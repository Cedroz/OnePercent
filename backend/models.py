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