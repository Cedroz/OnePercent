import os
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

load_dotenv()

MODEL = "gemini-3.6-flash"
# Guard so importing this module doesn't crash if the key is missing (e.g. prod
# not configured yet); the function fails at call time in that case.
_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=_key) if _key else None


# The shape of ONE task the AI must produce. Gemini fills a list of these.
class PlannedTask(BaseModel):
    title: str
    points: int
    metric: str | None    # "easy"/"medium"/"hard" for LeetCode tasks, else null (manual)
    target: int | None     # how many to solve, else null


def generate_roadmap(goal):
    prompt = f"""You are a coding-career coach. Create a roadmap of 5 to 8 concrete,
    actionable tasks to help someone reach this goal: "{goal}".

    Rules:
    - Each task is one small, concrete action.
    - For LeetCode practice tasks: set "metric" to "easy", "medium", or "hard", and
    "target" to the number of problems (e.g. 5). These get auto-tracked. The harder the Leetcode practice task, lower the quantity.
    - For any other task (build a project, read something, apply, mock interview):
    set "metric" and "target" to null (checked off manually).
    - "points": 10 for easy tasks, 15-20 for medium effort, 25+ for hard/big tasks.
    - Make the mix realistic for the goal."""
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list[PlannedTask],
        },
    )
    return [t.model_dump() for t in resp.parsed]
