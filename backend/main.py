import os
import time
import json

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth, OAuthError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from google.genai import errors as genai_errors
from database import save_user, get_user, delete_user_data, save_leetcode_stats, set_leetcode_username, set_tracked_repo, get_tasks, complete_task, get_points_log, get_streak, get_all_user_ids, run_detection, set_goal_and_plan, regenerate_stale_plans, refresh_plan_if_stale
from pydantic import BaseModel
from leetcode import fetch_leetcode_stats, fetch_recent_ac
from crypto import decrypt_token

class LeetCodeUsername(BaseModel):
    username: str

class TrackedRepo(BaseModel):
    repo: str

class Goal(BaseModel):
    goal: str

# Refetch LeetCode only if the cached data is older than this (seconds).
CACHE_TTL = 3600


# Load variables from backend/.env into the environment (local dev only;
# in production, Vercel injects these from its dashboard instead).
load_dotenv()

# `app` is the whole web application. FastAPI is an ASGI app object —
# a server (uvicorn locally, Vercel in prod) imports this `app` and calls it
# for every incoming request.
app = FastAPI()

# --- CORS ---
# Middleware is code that runs on EVERY request/response, wrapping your routes.
# CORSMiddleware adds the "Access-Control-Allow-Origin" header that tells the
# browser which frontend origins are allowed to read our responses.
# Only these exact origins are permitted; anything else stays blocked.
allowed_origins = [
    "http://localhost:5173",   # Vite dev server (default port)
    "http://127.0.0.1:5173",   # same server, other spelling of localhost
    "http://localhost:5174",   # Vite falls back here if 5173 is taken
    "http://127.0.0.1:5174",
    "https://one-percent-frontend.vercel.app",   # live Vercel frontend (production)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,   # allow cookies/auth headers (needed for OAuth in Phase 1)
    allow_methods=["*"],      # allow GET, POST, etc.
    allow_headers=["*"],      # allow any request headers
)

# --- Session ---
# Gives us a signed cookie to stash small bits of per-user data across requests.
# Authlib uses it to remember the OAuth "state" between the login redirect and
# the callback (a CSRF guard). The secret_key signs the cookie so it can't be forged.
# os.getenv (not os.environ[...]) so a missing var doesn't crash the app on boot.
# Locally these come from .env; in production they'd come from Vercel's dashboard.
# The fallback secret is only a dev placeholder — real auth in prod needs a real one.
_on_vercel = bool(os.getenv("VERCEL"))
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-only-insecure-placeholder"),
    # Prod: the OAuth callback returns cross-site (github.com → our domain), so the
    # state cookie needs SameSite=None + Secure to be sent. Dev is http localhost,
    # where None isn't allowed, so use lax there.
    same_site="none" if _on_vercel else "lax",
    https_only=_on_vercel,
)

# --- OAuth (GitHub) ---
# Register GitHub as an OAuth provider. Authlib now knows our app's identity
# (client_id/secret) and GitHub's URLs, so it can build the login redirect and
# later exchange the code for a token.
oauth = OAuth()
oauth.register(
    name="github",
    client_id=os.getenv("GITHUB_CLIENT_ID"),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
    authorize_url="https://github.com/login/oauth/authorize",       # where we send the user (step 2)
    access_token_url="https://github.com/login/oauth/access_token", # where we trade code→token (step 6)
    api_base_url="https://api.github.com/",                          # base for later API calls
    client_kwargs={"scope": "read:user"},                           # profile only — public repos, no private access
)

# Where to send the user after a successful login. Defaults to the local Vite
# dev server; overridable via env var for production.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


# This decorator registers a route: "when a GET request hits /health, run this function."
# The function's return value gets automatically converted to JSON.
@app.get("/")
def home():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ping")
def ping():
    return {"status": "ok"}


# --- OAuth: step 1-2 of the dance ---
# The user hits this. We tell Authlib "start the GitHub login," passing the
# callback URL GitHub should return them to. Authlib builds the GitHub authorize
# URL (with our client_id + a random state) and returns a redirect response —
# so the user's browser gets bounced to GitHub's "Authorize OnePercent?" page.
@app.get("/auth/login")
async def login(request: Request):
    # Drop any stale OAuth state first — Authlib appends a new state each login and
    # accumulated entries bloat the cookie (browser drops it → mismatching_state).
    request.session.clear()
    # The whole login flow (login → GitHub → callback) must stay on ONE domain so the
    # state cookie is first-party throughout. In prod that's the BACKEND domain
    # (set OAUTH_REDIRECT_URI); in dev it's localhost via the Vite proxy.
    redirect_uri = os.getenv("OAUTH_REDIRECT_URI") or f"{FRONTEND_URL}/auth/callback"
    return await oauth.github.authorize_redirect(request, redirect_uri)


# --- OAuth: step 6-8 of the dance ---
# GitHub redirects the user here with ?code=...&state=... . This is where the
# real handshake completes.
@app.get("/auth/callback")
async def callback(request: Request):
    # Authlib checks the returned `state` against the one saved in our session
    # cookie (CSRF guard), then POSTs the `code` + client_secret to GitHub.
    try:
        token = await oauth.github.authorize_access_token(request)
    except OAuthError:
        # State mismatch / stale login → bounce back to log in again (not a 500).
        return RedirectResponse(FRONTEND_URL)

    # Use that token to call GitHub's API and fetch the logged-in user's profile.
    resp = await oauth.github.get("user", token=token)
    profile = resp.json()

    github_id = profile["id"]
    # Store the GitHub token SERVER-SIDE, encrypted. It never goes to the browser.
    save_user(github_id, token["access_token"])
    # Hand the frontend a signed session token in the URL fragment (#). The frontend
    # and API are on different domains, so a cross-site cookie would be blocked;
    # instead the frontend stores this and sends it as an Authorization header.
    session_token = create_session_token(github_id)
    return RedirectResponse(f"{FRONTEND_URL}/#token={session_token}")


# --- Session tokens (Bearer, not cookies — the two domains can't share a cookie) ---
# Signed with SESSION_SECRET so they can't be forged; expire after 7 days.
_serializer = URLSafeTimedSerializer(
    os.getenv("SESSION_SECRET", "dev-only-insecure-placeholder"), salt="op-session"
)
TOKEN_MAX_AGE = 7 * 24 * 3600

def create_session_token(user_id):
    return _serializer.dumps({"user_id": user_id})

def current_user_id(request: Request):
    # Read + verify the Bearer token from the Authorization header; None if absent/bad.
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        data = _serializer.loads(auth[7:], max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")


# Helper: resolve the logged-in user's GitHub token, or reject with 401.
def require_login(request: Request):
    user_id = current_user_id(request)
    user = get_user(user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"access_token": decrypt_token(user.github_token), "token_type": "bearer"}



# Who is logged in? The frontend calls this to know whether to show a login
# button or the dashboard.
@app.get("/api/me")
async def me(request: Request):
    token = require_login(request)
    profile = (await oauth.github.get("user", token=token)).json()
    user = get_user(current_user_id(request))
    return {
        "login": profile["login"],
        "name": profile.get("name"),
        "avatar_url": profile.get("avatar_url"),
        "big_goal": user.big_goal if user else None,
        "goal_started_at": user.goal_started_at if user else None,
        "plan_overview": json.loads(user.plan_overview) if user and user.plan_overview else None,
        "tracked_repo": user.tracked_repo if user else None,
        "plan_updated_at": user.plan_updated_at if user else None,
    }


# Set the user's goal → generate an AI roadmap → it becomes their tasks.
# Gemini is called here only (never on page load).
@app.post("/api/goal")
def set_goal(body: Goal, request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        tasks = set_goal_and_plan(user_id, body.goal)
    except genai_errors.APIError:
        # Rate-limited (free tier is ~20/day) or the model is overloaded.
        raise HTTPException(
            status_code=503,
            detail="The AI is busy or hit its daily limit. Please try again in a bit.",
        )
    return {"tasks": tasks}


# The user's recent commits, pulled live from GitHub using their token.
# Strategy: find their most-recently-pushed repos, then read each repo's latest
# commits directly. (The events feed is laggy for fresh accounts, so we read
# commits straight from the source instead — this is live, not cached.)
@app.get("/api/commits")
async def commits(request: Request):
    token = require_login(request)
    profile = (await oauth.github.get("user", token=token)).json()
    login = profile["login"]

    # Their public repos, most recently pushed first.
    repos = (await oauth.github.get(
        f"users/{login}/repos?sort=pushed&per_page=5", token=token
    )).json()

    result = []
    for repo in repos if isinstance(repos, list) else []:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        commit_list = (await oauth.github.get(
            f"repos/{full_name}/commits?per_page=10", token=token
        )).json()
        for commit in commit_list if isinstance(commit_list, list) else []:
            # GitHub nests the message under commit["commit"]["message"].
            message = commit.get("commit", {}).get("message", "").split("\n")[0]
            result.append({
                "repo": full_name,
                "message": message,
                "sha": commit.get("sha", "")[:7],   # short hash, like git log shows
            })

    return {"login": login, "commits": result[:20]}

@app.get("/api/repos")
async def get_repos(request: Request):
    token = require_login(request)
    profile = (await oauth.github.get("user", token=token)).json()
    login = profile["login"]
    repos = (await oauth.github.get(
    f"users/{login}/repos?sort=pushed&per_page=100", token=token
    )).json()
    result = []
    for repo in repos if isinstance(repos, list) else []:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        result.append({
            "repo": full_name,
            "description": repo.get("description"),
        })
    return result

@app.post("/api/leetcode/username")
def set_leetcode(body: LeetCodeUsername, request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    set_leetcode_username(user_id, body.username)
    return {"ok": True}

# Pick the one repo whose commits get auto-tracked toward "make N commits" tasks.
@app.post("/api/github/repo")
def set_repo(body: TrackedRepo, request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    set_tracked_repo(user_id, body.repo)
    return {"ok": True}


# --- account / settings actions ---

@app.post("/auth/logout")
def logout(request: Request):
    request.session.clear()   # drop the session → next /api/me is "not logged in"
    return {"ok": True}

@app.post("/api/leetcode/disconnect")
def disconnect_leetcode(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    set_leetcode_username(user_id, None)
    return {"ok": True}

@app.post("/api/github/repo/disconnect")
def disconnect_repo(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    set_tracked_repo(user_id, None)
    return {"ok": True}

@app.post("/api/account/delete")
def delete_account(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    delete_user_data(user_id)   # wipe all data + the account row
    request.session.clear()     # and log them out
    return {"ok": True}

@app.get("/api/leetcode")
def get_leetcode(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    user = get_user(user_id)
    if user is None or user.leetcode_username is None:
        return {"username": None, "stats": None}

    # THE FRESHNESS CHECK: is the cache younger than CACHE_TTL seconds?
    #   time.time()            = now (Unix seconds)
    #   user.leetcode_updated_at = when we last cached
    #   the difference          = how old the cache is
    if user.leetcode_updated_at is not None and time.time() - user.leetcode_updated_at < CACHE_TTL:
        stats = {
            "Easy": user.leetcode_easy,
            "Medium": user.leetcode_medium,
            "Hard": user.leetcode_hard,
            "All": (user.leetcode_easy or 0) + (user.leetcode_medium or 0) + (user.leetcode_hard or 0),
        }
        return {"username": user.leetcode_username, "stats": stats, "cached": True}

    # Stale or never fetched → call LeetCode, save the fresh counts, return them.
    fresh = fetch_leetcode_stats(user.leetcode_username)
    save_leetcode_stats(user_id, fresh.get("Easy", 0), fresh.get("Medium", 0), fresh.get("Hard", 0))
    return {"username": user.leetcode_username, "stats": fresh, "cached": False}


# The user's task list (seeds the starter roadmap on first call).
@app.get("/api/tasks")
def tasks_endpoint(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    return {"tasks": get_tasks(user_id)}


# Mark a task complete. {task_id} is a PATH parameter — FastAPI pulls it out of
# the URL and passes it in as `task_id`.
@app.post("/api/tasks/{task_id}/complete")
def complete_task_endpoint(task_id: int, request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    result = complete_task(user_id, task_id)
    if result is None:
        raise HTTPException(404, "Task not found")
    return {"ok": True}


# Streak (consecutive active days) + points history, from the points_log.
@app.get("/api/stats")
def stats_endpoint(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    return {"streak": get_streak(user_id), "history": get_points_log(user_id)}


# Roll the daily plan over if a new Pacific day has begun. The dashboard calls
# this on load so tasks refresh at midnight PT without waiting for the cron.
@app.post("/api/plan/refresh")
def plan_refresh(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    regenerated = refresh_plan_if_stale(user_id)
    return {"regenerated": regenerated}


# The user's most recent accepted LeetCode problems, for display in the app.
@app.get("/api/leetcode/recent")
def leetcode_recent(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    user = get_user(user_id)
    if user is None or user.leetcode_username is None:
        return {"recent": []}
    return {"recent": fetch_recent_ac(user.leetcode_username)}


# On-demand detection for the logged-in user — lets the dashboard sync their
# LeetCode/GitHub activity immediately instead of waiting for the daily cron.
@app.post("/api/detect")
def detect_me(request: Request):
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    completed = run_detection(user_id)
    return {"completed": completed}


# Cron endpoint — Vercel Cron hits this on a schedule to run detection for EVERY
# user. Protected by a shared secret so random visitors can't trigger it.
@app.get("/api/cron/detect")
def cron_detect(request: Request):
    if request.headers.get("authorization") != f"Bearer {os.getenv('CRON_SECRET')}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    results = {}
    for github_id in get_all_user_ids():
        done = run_detection(github_id)
        if done:
            results[str(github_id)] = done
    # After logging yesterday's completions (which feed the context), refresh any
    # plan older than 24h with a fresh, progress-aware set of daily tasks.
    regenerated = regenerate_stale_plans()
    return {"detected": results, "regenerated": regenerated}

