"""
LinkedIn Enrichment Bridge Service
Runs on port 8001 alongside the main backend (port 8000).

During "Ask My Network" searches, the backend pushes usernames that need
enrichment to this service. This service maintains a queue that Claude Code
(with LinkedIn MCP access) processes automatically.

Flow:
  1. Backend POST /enqueue → adds usernames to the queue
  2. Claude Code GET /queue → picks up pending usernames
  3. Claude Code calls LinkedIn MCP to fetch profiles
  4. Claude Code POST /submit → stores enrichment data
  5. Backend GET /fetch/{username} → retrieves enrichment for ranking

Usage:
  python3 enrichment_service.py
"""

import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = Path(__file__).parent
CACHE_PATH = BASE / "enrichment_cache.json"

# In-memory queue of usernames pending enrichment
pending_queue: list[str] = []
processing: set[str] = set()


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


class EnqueueRequest(BaseModel):
    usernames: list[str]


class SubmitRequest(BaseModel):
    username: str
    raw_text: str


class LookupRequest(BaseModel):
    username: str


@app.get("/health")
def health():
    return {"status": "ok", "pending": len(pending_queue), "processing": len(processing)}


@app.post("/enqueue")
def enqueue(req: EnqueueRequest):
    """Backend calls this to request enrichment for usernames."""
    cache = load_cache()
    added = 0
    for username in req.usernames:
        if username not in cache and username not in processing and username not in pending_queue:
            pending_queue.append(username)
            added += 1
    print(f"  Enqueued {added} usernames for enrichment ({len(pending_queue)} total pending)")
    return {"enqueued": added, "pending": len(pending_queue)}


@app.get("/queue")
def get_queue():
    """Claude Code polls this to pick up usernames to enrich."""
    return {"pending": pending_queue[:], "processing": list(processing)}


@app.post("/claim")
def claim():
    """Claude Code claims the next username to process."""
    if not pending_queue:
        return {"username": None}
    username = pending_queue.pop(0)
    processing.add(username)
    return {"username": username}


@app.post("/submit")
def submit(req: SubmitRequest):
    """Claude Code submits enrichment data after fetching a profile."""
    cache = load_cache()
    enrichment = {"raw_text": req.raw_text, "username": req.username}
    cache[req.username] = enrichment
    save_cache(cache)
    processing.discard(req.username)
    print(f"  Enriched and cached: {req.username}")
    return {"status": "cached", "username": req.username}


@app.post("/lookup")
def lookup(req: LookupRequest):
    """Backend calls this to check if enrichment is available."""
    cache = load_cache()
    if req.username in cache:
        return cache[req.username]
    return {"raw_text": "", "username": req.username, "status": "not_cached"}


@app.get("/fetch/{username}")
def fetch(username: str):
    """Backend fetches enrichment data for a specific username."""
    cache = load_cache()
    if username in cache:
        return cache[username]
    return {"raw_text": "", "username": username, "status": "not_cached"}


@app.post("/wait-for-enrichment")
def wait_for_enrichment(req: EnqueueRequest):
    """
    Backend calls this to enqueue AND wait for enrichment.
    Returns immediately with the list of usernames that need processing.
    The backend should poll /fetch/{username} to check when they're done.
    """
    cache = load_cache()
    already_cached = []
    need_enrichment = []

    for username in req.usernames:
        if username in cache:
            already_cached.append(username)
        else:
            need_enrichment.append(username)
            if username not in processing and username not in pending_queue:
                pending_queue.append(username)

    print(f"  {len(already_cached)} already cached, {len(need_enrichment)} need enrichment")
    return {
        "cached": len(already_cached),
        "pending": len(need_enrichment),
        "usernames_pending": need_enrichment,
    }


if __name__ == "__main__":
    import uvicorn
    print("\n  LinkedIn Enrichment Service running on http://localhost:8001")
    print("  The backend will push usernames here during searches.")
    print("  Claude Code will process the queue using LinkedIn MCP.\n")
    uvicorn.run(app, host="0.0.0.0", port=8001)
