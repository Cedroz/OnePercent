from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    # Later, at deploy time, we'll add the live Vercel frontend URL here.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,   # allow cookies/auth headers (needed for OAuth in Phase 1)
    allow_methods=["*"],      # allow GET, POST, etc.
    allow_headers=["*"],      # allow any request headers
)


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