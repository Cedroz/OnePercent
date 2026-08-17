import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine
from models import User

load_dotenv() 

DATABASE_URL = os.getenv('DATABASE_URL')

engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
