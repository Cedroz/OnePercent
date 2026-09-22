import os
import re
import time
import random
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel
from leetcode import fetch_problem

load_dotenv()

# Models to try, most preferred first. Free-tier quota is metered per model, so when
# the top choice is spent for the day we can keep serving users on the next one down.
MODELS = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
# Cap how long any single request may hang. An overloaded model can sit on a request
# for ~50s before finally returning 503, which alone outlasts the serverless function.
# A real generation takes a second or two, so anything near this limit is a dead end
# and we're better off failing fast and asking the next model.
_REQUEST_TIMEOUT_MS = 15_000

# Guard so importing this module doesn't crash if the key is missing (e.g. prod
# not configured yet); the function fails at call time in that case.
_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(
    api_key=_key, http_options={"timeout": _REQUEST_TIMEOUT_MS}
) if _key else None

# Transient Gemini failures we should retry (overloaded / gateway), rather than
# letting a one-off blip kill a whole generation.
_RETRYABLE = {500, 502, 503, 504}


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


# Model name -> unix time when it's worth trying again. A model that's out of daily
# quota (or has been retired) stays skipped until then, so we go straight to one that
# can actually answer instead of spending a round trip proving it can't.
_unavailable_until = {}

# Free-tier daily quotas roll over at midnight Pacific.
_QUOTA_TZ = ZoneInfo("America/Los_Angeles")


def _quota_reset_ts():
    # Unix time of the next midnight Pacific.
    now = datetime.now(_QUOTA_TZ)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def _usable_models():
    now = time.time()
    usable = [m for m in MODELS if _unavailable_until.get(m, 0) <= now]
    # Everything is marked spent → try the whole list anyway. Our bookkeeping may be
    # stale (quota reset early, key upgraded), and being wrong costs only a 429.
    return usable or list(MODELS)


# A model that's merely busy or short-window throttled gets a brief rest while we ask
# the next one, rather than being written off for the day.
_SOFT_COOLDOWN = 60.0     # seconds
_RETIRED_COOLDOWN = 86400.0

# Backstop on the whole chain. Per-request timeouts already bound a single sweep; this
# only stops us starting *extra* sweeps when the clock has run on.
_TIME_BUDGET = 45.0       # seconds per _generate call


# What callers should catch: the AI couldn't answer, for a reason that's about the
# service rather than the request. main.py turns this into a friendly 503.
AI_UNAVAILABLE = (genai_errors.APIError, httpx.TimeoutException)


def _cooldown_for(e):
    # How long this model should sit out, or None if the error isn't one that another
    # model could dodge (bad key, malformed request — every model fails identically).
    if isinstance(e, httpx.TimeoutException):
        return _SOFT_COOLDOWN       # sitting on the request; give someone else a turn
    code = getattr(e, "code", None)
    if _is_daily_quota(e):
        return _quota_reset_ts() - time.time()      # spent; nothing until tomorrow
    if code == 404:
        return _RETIRED_COOLDOWN                    # retired, or not enabled for this key
    if code == 429:
        # Short-window throttle: rest it for as long as the server asks, within reason.
        hint = _retry_after(e)
        return min(hint, _SOFT_COOLDOWN) if hint else _SOFT_COOLDOWN
    if code in _RETRYABLE:
        return _SOFT_COOLDOWN                       # overloaded or a gateway blip
    return None


def _generate(prompt, config, sweeps=2):
    # Sweep the model list, giving each one a single attempt before retrying any of
    # them. Breadth first on purpose: when the preferred model is slow to fail, burning
    # the time budget on retrying *it* would starve a healthy model further down.
    deadline = time.time() + _TIME_BUDGET
    last_error = None
    delay = 1.0
    for sweep in range(sweeps):
        for model in _usable_models():
            # Every model gets one shot on the first sweep even if the clock is nearly
            # gone: a healthy model usually answers in about a second, and skipping it
            # because a *different* model hung would throw away the whole point of the
            # fallback chain. Later sweeps are just retries, so those we do drop.
            if sweep > 0 and time.time() >= deadline:
                print("[planner] out of time; giving up before trying more models")
                raise last_error
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
                _unavailable_until.pop(model, None)   # it's healthy; forget any old mark
                return resp
            except AI_UNAVAILABLE as e:
                cooldown = _cooldown_for(e)
                if cooldown is None:
                    raise
                _unavailable_until[model] = time.time() + cooldown
                reason = getattr(e, "code", None) or type(e).__name__
                print(f"[planner] {model} unavailable ({reason}); trying next model")
                last_error = e
        # Every model is parked past our deadline (all daily-spent, say) — another
        # sweep would only collect the same rejections.
        if all(_unavailable_until.get(m, 0) > deadline for m in MODELS):
            break
        # A whole sweep failed. Back off a little before going round again, in case the
        # whole API is having a moment — but only if there's time left to be worth it.
        wait = delay + random.uniform(0, 0.5)   # jitter avoids thundering-herd
        if sweep == sweeps - 1 or time.time() + wait >= deadline:
            break
        time.sleep(wait)
        delay *= 2
    raise last_error     # nothing could serve us; caller turns this into a 503


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
