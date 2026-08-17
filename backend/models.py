from sqlmodel import SQLModel, Field

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(unique=True, index=True)
    github_token: str
    leetcode_username: str | None = None
    big_goal: str | None = None