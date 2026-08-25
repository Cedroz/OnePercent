import os
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session, select
from models import User, Task, PointsLog
from crypto import encrypt_token

load_dotenv() 

DATABASE_URL = os.getenv('DATABASE_URL')

# Only build the engine if a URL is present, so importing this module doesn't
# crash when DATABASE_URL is missing (e.g. on Vercel, which isn't configured
# with it yet). Locally it comes from .env, so the engine works normally.
engine = create_engine(DATABASE_URL) if DATABASE_URL else None

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def save_user(github_id, access_token):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.github_id == github_id)).first()
        if user == None:
                user = User(github_id=github_id, github_token=encrypt_token(access_token))
        else:
                user.github_token = encrypt_token(access_token)
        session.add(user)
        session.commit()

def get_user(github_id):
    with Session(engine) as session:
        return session.exec(select(User).where(User.github_id == github_id)).first()

def set_leetcode_username(github_id, username):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.github_id == github_id)).first()
        if user == None:
            return
        else:
            user.leetcode_username = username
        session.add(user)
        session.commit()

def save_leetcode_stats(github_id, easy, medium, hard):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.github_id == github_id)).first()
        if user is None:
            return
        user.leetcode_easy = easy
        user.leetcode_medium = medium
        user.leetcode_hard = hard
        user.leetcode_updated_at = time.time()   # record WHEN we cached it (Unix seconds)
        session.add(user)
        session.commit()


# A hardcoded starter roadmap. New users get seeded with these (Phase 3 template).
STARTER_TASKS = [
    ("Solve 5 easy LeetCode problems", 10),
    ("Solve 3 medium LeetCode problems", 20),
    ("Solve 1 hard LeetCode problem", 25),
    ("Make 5 GitHub commits", 10),
    ("Merge 1 pull request", 15),
]

def get_tasks(github_id):
    with Session(engine) as session:
        tasks = session.exec(select(Task).where(Task.github_id == github_id)).all()
        if not tasks:
            # First time for this user → seed the starter roadmap.
            for title, points in STARTER_TASKS:
                session.add(Task(github_id=github_id, title=title, points=points))
            session.commit()
            tasks = session.exec(select(Task).where(Task.github_id == github_id)).all()
        # Return plain dicts (safe to use after the session closes).
        return [
            {"id": t.id, "title": t.title, "points": t.points, "completed": t.completed}
            for t in tasks
        ]

def complete_task(github_id, task_id):
    with Session(engine) as session:
        # Match BOTH id and github_id, so a user can only complete THEIR OWN task
        # (can't flip someone else's task by guessing an id).
        task = session.exec(
            select(Task).where(Task.id == task_id, Task.github_id == github_id)
        ).first()
        if task is None:
            return None
        if task.completed:
            return {"id": task.id, "points": 0}   # already done → don't double-award
        task.completed = True
        session.add(task)
        # Log the award (powers history + streak).
        session.add(PointsLog(
            github_id=github_id,
            task_title=task.title,
            points=task.points,
            created_at=time.time(),
        ))
        session.commit()
        return {"id": task.id, "points": task.points}


def get_points_log(github_id):
    with Session(engine) as session:
        logs = session.exec(
            select(PointsLog)
            .where(PointsLog.github_id == github_id)
            .order_by(PointsLog.created_at.desc())   # newest first
        ).all()
        return [
            {"task_title": l.task_title, "points": l.points, "created_at": l.created_at}
            for l in logs
        ]


def get_streak(github_id):
    # Consecutive days (UTC) on which the user earned points.
    with Session(engine) as session:
        logs = session.exec(select(PointsLog).where(PointsLog.github_id == github_id)).all()

    # Set of distinct dates the user was active.
    days = {datetime.fromtimestamp(l.created_at, tz=timezone.utc).date() for l in logs}
    if not days:
        return 0

    today = datetime.now(timezone.utc).date()
    # Anchor on today if active today, else yesterday (a streak isn't "broken"
    # until a whole day passes with no activity).
    if today in days:
        day = today
    elif (today - timedelta(days=1)) in days:
        day = today - timedelta(days=1)
    else:
        return 0

    # Walk backwards day by day while each day has activity.
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak