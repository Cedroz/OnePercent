import os
import time
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session, select
from models import User
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