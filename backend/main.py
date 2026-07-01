from fastapi import FastAPI

# `app` is the whole web application. FastAPI is an ASGI app object —
# a server (uvicorn locally, Vercel in prod) imports this `app` and calls it
# for every incoming request.
app = FastAPI()


# This decorator registers a route: "when a GET request hits /health, run this function."
# The function's return value gets automatically converted to JSON.
@app.get("/health")
def health():
    return {"status": "ok"}
