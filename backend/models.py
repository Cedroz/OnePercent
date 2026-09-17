from sqlmodel import SQLModel, Field

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(unique=True, index=True)
    github_token: str
    leetcode_username: str | None = None
    tracked_repo: str | None = None      # one repo to track, e.g. "Cedroz/OnePercent"
    big_goal: str | None = None
    plan_overview: str | None = None      # JSON: start-to-finish phased roadmap for the goal
    plan_updated_at: float | None = None  # when the daily task plan was last generated (Unix seconds)
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
    # Auto-detection fields (None = manual task, not auto-detected):
    metric: str | None = None            # "easy" / "medium" / "hard"
    target: int | None = None            # how many to solve
    baseline: int | None = None          # metric count when detection started tracking this task
    resource_url: str | None = None      # optional tutorial link (e.g. a YouTube search) for the task
    leetcode_slug: str | None = None     # specific problem to auto-complete when solved (e.g. "two-sum")


class PointsLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(index=True)   # owner
    task_title: str                      # what was completed
    points: int                          # points awarded
    created_at: float                    # Unix seconds — used for history + streak

class Snapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(index=True) 
    leetcode_easy: int
    leetcode_medium: int
    leetcode_hard: int
    commit_count: int 
    created_at: float   