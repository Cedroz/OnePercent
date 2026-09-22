import os
import re
import time
import random
from urllib.parse import quote_plus
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel
from leetcode import fetch_problem

load_dotenv()

MODEL = "gemini-3.6-flash"
# Guard so importing this module doesn't crash if the key is missing (e.g. prod
# not configured yet); the function fails at call time in that case.
_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=_key) if _key else None

# Transient Gemini failures we should retry (overloaded / gateway), rather than
# letting a one-off blip kill a whole generation.
_RETRYABLE = {500, 502, 503, 504}

# A 429 is only worth retrying when it's a short per-minute throttle. A DAILY quota
# can't be waited out inside a request, and on the free tier it's small (20/day per
# model) — every retry spends another request from it, so retrying a daily-quota 429
# burns the remaining budget 4x per failure for nothing.
_MAX_RETRY_AFTER = 30.0   # seconds; a hint longer than this isn't worth holding for


def _error_details(e):
    # google-genai puts the raw error body on .details as {"error": {..., "details": [...]}}.
    return (getattr(e, "details", None) or {}).get("error", {}).get("details", []) or []


def _is_daily_quota(e):
    # A QuotaFailure violation names the quota it broke, e.g.
    # "GenerateRequestsPerDayPerProjectPerModel-FreeTier". Per-day means come back
    # tomorrow, so there is nothing to retry.
    for detail in _error_details(e):
        for violation in detail.get("violations", []) or []:
            if "PerDay" in str(violation.get("quotaId", "")):
                return True
    return False


def _retry_after(e):
    # Gemini returns a RetryInfo detail like {"retryDelay": "33s"} on a 429.
    # Returns the delay in seconds, or None when the error carries no hint.
    for detail in _error_details(e):
        match = re.fullmatch(r"([\d.]+)s", str(detail.get("retryDelay", "")))
        if match:
            return float(match.group(1))
    return None


def _generate(prompt, config, attempts=4):
    # Call Gemini with exponential backoff + jitter on transient errors.
    delay = 1.0
    for i in range(attempts):
        try:
            return client.models.generate_content(model=MODEL, contents=prompt, config=config)
        except genai_errors.APIError as e:
            code = getattr(e, "code", None)
            wait = delay + random.uniform(0, 0.5)   # jitter avoids thundering-herd
            if code == 429:
                # Retry a short per-minute throttle; give up on a daily quota so we
                # don't spend the rest of the day's budget on doomed attempts.
                hint = _retry_after(e)
                if _is_daily_quota(e) or hint is None or hint > _MAX_RETRY_AFTER:
                    raise
                wait = hint + random.uniform(0, 0.5)
            elif code not in _RETRYABLE:
                raise
            if i == attempts - 1:   # out of attempts → let the caller handle it
                raise
            time.sleep(wait)
            delay *= 2              # 1s → 2s → 4s


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


# One phase of the big-picture, start-to-finish roadmap toward the goal.
class Phase(BaseModel):
    title: str        # e.g. "Phase 1: Core CS fundamentals"
    focus: str        # what they concretely work on in this phase
    why: str          # why this phase matters toward the goal
    duration: str     # rough timeframe, e.g. "3-4 weeks"

class Overview(BaseModel):
    summary: str          # 1-2 sentence overall strategy
    phases: list[Phase]


def generate_overview(goal, context=""):
    prompt = f"""You are a coding-career coach. Lay out a realistic START-TO-FINISH
    roadmap for reaching this goal: "{goal}". Break the whole journey into 4 to 6
    sequential phases, from where they are now to actually achieving the goal.

    {context}

    For each phase provide:
    - "title": a short phase name (e.g. "Phase 1: Core CS fundamentals").
    - "focus": what they concretely work on in this phase (1-2 sentences).
    - "why": why this phase matters — how it moves them toward the goal (1-2 sentences).
    - "duration": a rough timeframe (e.g. "3-4 weeks").
    Also give "summary": 1-2 sentences describing the overall strategy.

    Be realistic and specific to the goal and their current level."""
    resp = _generate(prompt, {
        "response_mime_type": "application/json",
        "response_schema": Overview,
    })
    ov = resp.parsed
    return {
        "summary": ov.summary,
        "phases": [{"title": p.title, "focus": p.focus, "why": p.why, "duration": p.duration}
                   for p in ov.phases],
    }


def _phases_text(overview):
    # Render the stored overview into a compact phase list for the daily prompt.
    if not overview or not overview.get("phases"):
        return ""
    lines = [f'{i+1}. {p["title"]} — {p["focus"]}' for i, p in enumerate(overview["phases"])]
    return (
        "Here is the overall multi-phase plan for this goal:\n"
        + "\n".join(lines)
        + "\n\nWork out which phase they are CURRENTLY in from their progress above "
        "(early on = phase 1), and make today's tasks concrete steps WITHIN that phase. "
        "Do not jump ahead to later phases."
    )


def generate_roadmap(goal, context="", overview=None):
    prompt = f"""You are a coding-career coach. "{goal}" is a LONG-TERM goal that takes
    weeks or months of steady daily effort. Create just TODAY's small set of 3 to 4
    daily tasks — one day's worth of steady progress, NOT everything needed to reach
    the goal.

    {_phases_text(overview)}

    {context}

    Rules:
    - EVERY task must directly serve the goal "{goal}". If their past history (below)
    is about a different topic, IGNORE that topic — use the history only to gauge their
    level and avoid repeating work, NOT to choose subjects. (e.g. if the goal is a
    general software / Google role, do not assign embedded/firmware/hardware tasks just
    because they did them before.)
    - Keep it SMALL and realistic for ONE day: 3 to 4 tasks, roughly 1 hour of focused
    work total. Do not overload the day.
    - Daily tasks are small, incremental, mostly repeatable practice and study — the
    kind of thing you do again (a little harder) the next day. They are steps toward
    the goal, never the finish line.
    - Do NOT include one-time MILESTONE actions as daily tasks: no "apply to the job",
    no full "mock interview", no "read the entire style guide". Those happen rarely, not
    daily. At most ONE light study/reading task per day, and keep it small.
    - Build on what they've already done (above): don't repeat finished work; pick the
    sensible next step and gradually increase difficulty over time.
    - For GENERAL LeetCode practice: set "metric" to "easy", "medium", or "hard", and
    "target" to a small number of problems (1-3), and leave "leetcode_slug" null. The
    harder the practice, the lower the quantity.
    - If the goal names a SPECIFIC company (e.g. Google, Rivian, Meta): include at most
    1 or 2 SPECIFIC, well-known problems that company is known to ask (or very close
    variants). For each, make its own task titled like "Solve LeetCode: <Problem Name>",
    set "leetcode_slug" to the real URL slug (e.g. "two-sum", "lru-cache"), "metric" to
    its difficulty, and "target" to 1. Only use real, famous problems — never invent slugs.
    - For GitHub coding tasks (make progress on their project): set "metric" to "commits"
    and "target" to a small number (1-3). Auto-tracked against their chosen repo. At most
    one commits task.
    - "youtube_query": ONLY for a topic they likely have little experience with, give a
    short search phrase for a beginner tutorial (e.g. "binary search tutorial for
    beginners"). For familiar/simple tasks leave it null.
    - Any non-tracked task sets "metric" and "target" to null (checked off manually).
    - "points": 10 for easy tasks, 15-20 for medium effort, 25+ for hard/big tasks.
    - Make the mix realistic for one day at their current level."""
    resp = _generate(prompt, {
        "response_mime_type": "application/json",
        "response_schema": list[PlannedTask],
    })
    tasks = []
    for t in resp.parsed:
        metric = t.metric
        target = t.target
        resource_url = None
        slug = None

        # A specific problem was suggested → verify it's real before linking/tracking.
        if t.leetcode_slug:
            problem = fetch_problem(t.leetcode_slug)
            if problem:
                slug = t.leetcode_slug            # store it so detection can match a solve
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
            "leetcode_slug": slug,
        })
    return tasks
