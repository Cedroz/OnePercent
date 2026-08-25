from sqlmodel import SQLModel, Field

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(unique=True, index=True)
    github_token: str
    leetcode_username: str | None = None
    big_goal: str | None = None
    # Cached LeetCode stats + when they were last fetched (Unix seconds).
    # We read these instead of calling LeetCode, and only refetch when stale.
    leetcode_easy: int | None = None
    leetcode_medium: int | None = None
    leetcode_hard: int | None = None
    leetcode_updated_at: float | None = None


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(index=True)   # owner; indexed but NOT unique (many tasks per user)
    title: str                           # e.g. "Solve 5 medium LeetCode problems"
    points: int                          # awarded when completed
    completed: bool = False


class PointsLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(index=True)   # owner
    task_title: str                      # what was completed
    points: int                          # points awarded
    created_at: float                    # Unix seconds — used for history + streak