import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth

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
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-only-insecure-placeholder"),
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
    client_kwargs={"scope": "read:user"},                           # what we're asking permission for
)

# TEMPORARY in-memory token store (Phase 1 only). Maps GitHub user id -> token.
# This is wiped on restart and does NOT work on serverless (no shared memory
# between requests) — we replace it with the encrypted DB store in Phase 2.
# Good enough for local dev right now.
TOKENS = {}

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
    # Callback comes back through the frontend origin (Vite proxies it to us),
    # so the whole flow stays on ONE origin and the session cookie survives.
    redirect_uri = "http://localhost:5173/auth/callback"
    return await oauth.github.authorize_redirect(request, redirect_uri)


# --- OAuth: step 6-8 of the dance ---
# GitHub redirects the user here with ?code=...&state=... . This is where the
# real handshake completes.
@app.get("/auth/callback")
async def callback(request: Request):
    # Authlib checks the returned `state` against the one saved in our session
    # cookie (CSRF guard), then POSTs the `code` + our client_secret to GitHub
    # and gets back an access token. All the sensitive bits happen server-side.
    token = await oauth.github.authorize_access_token(request)

    # Use that token to call GitHub's API and fetch the logged-in user's profile.
    resp = await oauth.github.get("user", token=token)
    profile = resp.json()

    github_id = profile["id"]
    # Store the token SERVER-SIDE, keyed by GitHub id. It never goes to the browser.
    TOKENS[github_id] = token
    # Remember who this browser is: put the (non-secret) user id in the signed cookie.
    request.session["user_id"] = github_id

    # Send the user back to the frontend — they're now logged in (session cookie set).
    return RedirectResponse(FRONTEND_URL)


# Helper: pull the current user's token from the session, or reject with 401.
# Any endpoint that needs GitHub access calls this first.
def require_login(request: Request):
    user_id = request.session.get("user_id")
    if user_id is None or user_id not in TOKENS:
        raise HTTPException(status_code=401, detail="Not logged in")
    return TOKENS[user_id]


# Who is logged in? The frontend calls this to know whether to show a login
# button or the dashboard.
@app.get("/api/me")
async def me(request: Request):
    token = require_login(request)
    profile = (await oauth.github.get("user", token=token)).json()
    return {
        "login": profile["login"],
        "name": profile.get("name"),
        "avatar_url": profile.get("avatar_url"),
    }


# The user's recent commits, pulled live from GitHub using their token.
# Strategy: find their most-recently-pushed repos, then read each repo's latest
# commits directly. (The events feed is laggy for fresh accounts, so we read
# commits straight from the source instead — this is live, not cached.)
@app.get("/api/commits")
async def commits(request: Request):
    token = require_login(request)
    profile = (await oauth.github.get("user", token=token)).json()
    login = profile["login"]

    # Their repos, most recently pushed first.
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