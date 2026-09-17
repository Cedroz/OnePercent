import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel
from leetcode import fetch_problem

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
    metric: str | None    # "easy"/"medium"/"hard" (LeetCode) or "commits" (GitHub); else null (manual)
    target: int | None     # how many to solve, else null
    # Search terms for a beginner tutorial, ONLY when the task covers a topic the
    # user is likely new to. We turn this into a YouTube SEARCH link (never a
    # specific video URL — the model would hallucinate a fake video id).
    youtube_query: str | None
    # The exact LeetCode problem slug (e.g. "two-sum") when recommending a SPECIFIC
    # problem — used mainly for company-targeted goals. We verify it against
    # LeetCode before linking, since the model can invent slugs that 404.
    leetcode_slug: str | None


def _resource_url(query):
    # Build a YouTube search link from a query. A search link always resolves and
    # surfaces whatever is currently popular, unlike a hallucinated /watch?v= id.
    if not query:
        return None
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def generate_roadmap(goal, context=""):
    prompt = f"""You are a coding-career coach. Create a fresh set of 5 to 8 concrete,
    actionable DAILY tasks that move someone toward this goal: "{goal}".

    {context}

    Rules:
    - Each task is one small, concrete action they can do today.
    - Build on what they've already done (above): don't repeat finished work; pick
    the sensible next steps and gradually increase difficulty.
    - For GENERAL LeetCode practice: set "metric" to "easy", "medium", or "hard", and
    "target" to the number of problems (e.g. 5), and leave "leetcode_slug" null. The
    harder the practice, the lower the quantity.
    - If the goal names a SPECIFIC company (e.g. Google, Rivian, Meta): recommend 1-3
    SPECIFIC, well-known problems that company is known to ask (or very close variants).
    For each, make its own task titled like "Solve LeetCode: <Problem Name>", set
    "leetcode_slug" to the real URL slug (e.g. "two-sum", "lru-cache"), "metric" to its
    difficulty, and "target" to 1. Only use real, famous problems — never invent slugs.
    - For GitHub coding tasks (make progress on their project): set "metric" to
    "commits" and "target" to a number of commits (e.g. 5). Auto-tracked against the
    one repo they chose. Include at most one commits task.
    - For any other task (read something, apply, mock interview): set "metric" and
    "target" to null (checked off manually).
    - "youtube_query": ONLY for a topic they likely have little experience with, give
    a short search phrase for a beginner tutorial (e.g. "binary search tutorial for
    beginners"). For familiar/simple tasks leave it null.
    - "points": 10 for easy tasks, 15-20 for medium effort, 25+ for hard/big tasks.
    - Make the mix realistic for the goal and their current level."""
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list[PlannedTask],
        },
    )
    tasks = []
    for t in resp.parsed:
        metric = t.metric
        target = t.target
        resource_url = None

        # A specific problem was suggested → verify it's real before linking.
        if t.leetcode_slug:
            problem = fetch_problem(t.leetcode_slug)
            if problem:
                resource_url = f"https://leetcode.com/problems/{t.leetcode_slug}/"
                metric = problem["difficulty"]   # trust LeetCode's real difficulty
                target = 1                        # one specific problem to solve

        # No verified problem link → fall back to a YouTube tutorial search (if any).
        if resource_url is None:
            resource_url = _resource_url(t.youtube_query)

        tasks.append({
            "title": t.title,
            "points": t.points,
            "metric": metric,
            "target": target,
            "resource_url": resource_url,
        })
    return tasks
