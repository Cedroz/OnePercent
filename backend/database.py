import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session, select
from models import User

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
            user = User(github_id=github_id, github_token=access_token)
        else:
            user.github_token = access_token
        session.add(user)
        session.commit()

def get_user(github_id):
    with Session(engine) as session:
        return session.exec(select(User).where(User.github_id == github_id)).first()