"""
LinkedIn Enrichment Bridge Service
Runs on port 8001 alongside the main backend (port 8000).

This service wraps the LinkedIn MCP tools so the backend can fetch
LinkedIn profiles during the search pipeline.

Usage:
  python enrichment_service.py

The main backend calls POST /lookup {"username": "john-doe"} and gets
back profile data that gets cached in enrichment_cache.json.
"""

import json
import subprocess
import sys
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


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


class LookupRequest(BaseModel):
    username: str
    sections: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/lookup")
async def lookup_profile(req: LookupRequest):
    """
    Fetch a LinkedIn profile via Claude Code's LinkedIn MCP tools.

    This uses subprocess to call claude with the LinkedIn MCP tool.
    Falls back to returning None if the lookup fails.
    """
    # Check cache first
    cache = load_cache()
    if req.username in cache:
        return cache[req.username]

    # Use claude CLI to call the LinkedIn MCP tool
    prompt = f"""Use the mcp__linkedin__get_person_profile tool to fetch the LinkedIn profile for username "{req.username}".
Return ONLY the raw profile text content, nothing else. No commentary, no markdown formatting."""

    try:
        result = subprocess.run(
            ["claude", "--print", "--allowedTools", "mcp__linkedin__get_person_profile", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=45,
        )

        if result.returncode == 0 and result.stdout.strip():
            raw_text = result.stdout.strip()
            enrichment = {"raw_text": raw_text, "username": req.username}

            # Cache the result
            cache[req.username] = enrichment
            save_cache(cache)

            return enrichment
        else:
            print(f"  Claude CLI failed for {req.username}: {result.stderr[:200]}", file=sys.stderr)
            return {"raw_text": "", "username": req.username, "error": "lookup_failed"}

    except subprocess.TimeoutExpired:
        print(f"  Timeout fetching {req.username}", file=sys.stderr)
        return {"raw_text": "", "username": req.username, "error": "timeout"}
    except FileNotFoundError:
        print("  Claude CLI not found — install Claude Code first", file=sys.stderr)
        return {"raw_text": "", "username": req.username, "error": "claude_not_found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
