"""
Ask My Network — FastAPI backend
POST /ask with {"query": "..."} → SSE stream with progress + ranked enriched prospects

Pipeline:
  1. Claude AI pre-filter (Haiku, batched) — scans ALL connections intelligently
  2. Attach cached enrichment data (instant lookup)
  3. Claude deep rank (Sonnet) — final ranking + personalized outreach messages
  4. Results streamed via Server-Sent Events for real-time progress
"""

import asyncio
import csv
import json
import re
import sys
from pathlib import Path

import anthropic
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = Path(__file__).parent
CSV_PATH = BASE / "Connections.csv"
CACHE_PATH = BASE / "enrichment_cache.json"
CONFIG_PATH = BASE / "client_config.json"
PROSPECTS_PATH = BASE / "app" / "public" / "prospects.json"

PREFILTER_BATCH_SIZE = 100
PREFILTER_MODEL = "claude-haiku-4-5-20251001"
RANK_MODEL = "claude-sonnet-4-6"
MAX_TO_CLAUDE = 50
MAX_CONCURRENT_BATCHES = 3
ENRICHMENT_SERVICE_URL = "http://localhost:8001"
MAX_LIVE_ENRICHMENTS = 10  # Cap live LinkedIn lookups per search


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {
        "client_name": "User",
        "q1_ideal_prospects": "",
        "q2_industries_and_signals": "",
        "q3_voice": "Professional but friendly. Direct and concise.",
        "q4_cta": "Get on a call.",
    }


# ── CSV loading ──────────────────────────────────────────────────────────────

def load_connections() -> list[dict]:
    """Parse LinkedIn Connections.csv, skipping the notes header."""
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for line in reader:
            if line and line[0].strip() == "First Name":
                break
        for line in reader:
            if len(line) < 6:
                continue
            rows.append({
                "first_name": line[0].strip(),
                "last_name": line[1].strip(),
                "url": line[2].strip(),
                "email": line[3].strip(),
                "company": line[4].strip(),
                "position": line[5].strip(),
                "connected_on": line[6].strip() if len(line) > 6 else "",
            })
    return rows


def extract_username(url: str) -> str | None:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url)
    return m.group(1) if m else None


# ── Existing messages from Ranked List ────────────────────────────────────────

def load_existing_messages() -> dict:
    """Load pre-generated messages from prospects.json, keyed by LinkedIn URL."""
    if not PROSPECTS_PATH.exists():
        return {}
    try:
        data = json.loads(PROSPECTS_PATH.read_text())
        messages = {}
        for p in data.get("prospects", []):
            url = p.get("url", "")
            msg = p.get("message", "")
            if url and msg:
                messages[url] = msg
        return messages
    except (json.JSONDecodeError, KeyError):
        return {}


# ── Claude AI Pre-filter (Haiku, batched) ────────────────────────────────────

async def claude_prefilter_batch(
    client: anthropic.AsyncAnthropic,
    query: str,
    batch: list[dict],
    batch_offset: int,
    cfg: dict,
) -> list[int]:
    """Send one batch to Haiku and return global indices of relevant connections."""
    connections_text = "\n".join(
        f"[{i}] {c['first_name']} {c['last_name']} | {c['position']} | {c['company']} | Connected: {c['connected_on']}"
        for i, c in enumerate(batch)
    )

    prompt = f"""You are filtering LinkedIn connections for relevance to a search query.

Query: "{query}"

Client context:
- Ideal prospects: {cfg['q1_ideal_prospects']}
- Target industries & signals: {cfg['q2_industries_and_signals']}

For each connection below, decide if they MIGHT be relevant to the query. Be generous and inclusive — use your knowledge to infer things like:
- Company names that suggest an industry (e.g., "Free'eat" → food industry)
- Names that suggest a nationality or location
- Job titles in other languages (e.g., "Co-fondateur" = Co-founder)
- Companies that are known startups or in specific sectors

If there's any reasonable chance someone matches the query, include them.

Return ONLY a JSON array of the indices that are potentially relevant. Example: [0, 3, 7, 12]
If none are relevant, return an empty array: []

Connections:
{connections_text}"""

    response = await client.messages.create(
        model=PREFILTER_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    text = re.sub(r"^```json?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        local_indices = json.loads(text)
        if not isinstance(local_indices, list):
            return []
        return [batch_offset + i for i in local_indices if 0 <= i < len(batch)]
    except json.JSONDecodeError:
        print(f"  Haiku pre-filter returned invalid JSON: {text[:100]}", file=sys.stderr)
        return []


async def claude_prefilter(
    client: anthropic.AsyncAnthropic,
    query: str,
    connections: list[dict],
    cfg: dict,
    progress_callback=None,
) -> list[dict]:
    """Send all connections to Haiku in batches, return relevant candidates."""
    batches = []
    for i in range(0, len(connections), PREFILTER_BATCH_SIZE):
        batches.append((connections[i:i + PREFILTER_BATCH_SIZE], i))

    total_batches = len(batches)
    all_indices = []
    completed = 0

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)

    async def run_batch(batch, offset):
        nonlocal completed
        async with semaphore:
            result = await claude_prefilter_batch(client, query, batch, offset, cfg)
            completed += 1
            if progress_callback:
                await progress_callback("prefilter", completed, total_batches)
            return result

    tasks = [run_batch(batch, offset) for batch, offset in batches]
    results = await asyncio.gather(*tasks)

    for indices in results:
        all_indices.extend(indices)

    unique_indices = sorted(set(all_indices))
    return [connections[i] for i in unique_indices if i < len(connections)]


# ── Enrichment cache ─────────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def attach_cached_enrichment(candidates: list[dict]) -> list[dict]:
    """Attach any cached enrichment data to candidates. No scraping."""
    cache = load_cache()
    result = []
    for c in candidates:
        username = extract_username(c["url"])
        enrichment = cache.get(username) if username else None
        if enrichment:
            print(f"  Cache hit: {username}")
        result.append({**c, "enrichment": enrichment})
    return result


async def live_enrich_candidate(
    http_client: httpx.AsyncClient,
    username: str,
) -> dict | None:
    """Fetch a LinkedIn profile via the enrichment bridge service."""
    try:
        resp = await http_client.post(
            f"{ENRICHMENT_SERVICE_URL}/lookup",
            json={"username": username},
            timeout=30.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    return None


async def enrich_candidates(
    candidates: list[dict],
    progress_callback=None,
) -> list[dict]:
    """Enrich candidates: use cache first, then live LinkedIn lookup for uncached."""
    cache = load_cache()
    result = []
    to_enrich = []  # (index_in_result, username)

    for c in candidates:
        username = extract_username(c["url"])
        enrichment = cache.get(username) if username else None
        if enrichment:
            print(f"  Cache hit: {username}")
        result.append({**c, "enrichment": enrichment})
        if not enrichment and username:
            to_enrich.append((len(result) - 1, username))

    # Cap live lookups to avoid slow searches
    to_enrich = to_enrich[:MAX_LIVE_ENRICHMENTS]

    if not to_enrich:
        return result

    # Try live enrichment via the bridge service
    enriched_count = 0
    async with httpx.AsyncClient() as http_client:
        # Check if enrichment service is running
        try:
            health = await http_client.get(
                f"{ENRICHMENT_SERVICE_URL}/health", timeout=2.0
            )
            service_available = health.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            service_available = False

        if not service_available:
            print("  Enrichment service not running — using cache only")
            return result

        print(f"  Live enriching {len(to_enrich)} uncached profiles...")

        for idx, username in to_enrich:
            enrichment = await live_enrich_candidate(http_client, username)
            if enrichment:
                result[idx]["enrichment"] = enrichment
                # Save to cache for future searches
                cache[username] = enrichment
                enriched_count += 1
                print(f"  Enriched: {username}")
            if progress_callback:
                await progress_callback(enriched_count, len(to_enrich))

    if enriched_count > 0:
        save_cache(cache)
        print(f"  Live enriched {enriched_count}/{len(to_enrich)} profiles")

    return result


# ── Claude deep ranking (Sonnet) ─────────────────────────────────────────────

async def rank_with_claude(
    client: anthropic.AsyncAnthropic,
    query: str,
    candidates: list[dict],
) -> list[dict]:
    """Send candidates to Claude Sonnet for ranking + outreach messages."""
    cfg = load_config()
    existing_messages = load_existing_messages()

    candidate_text = ""
    for i, c in enumerate(candidates[:MAX_TO_CLAUDE]):
        enrichment = ""
        if c.get("enrichment") and c["enrichment"].get("raw_text"):
            enrichment = c["enrichment"]["raw_text"][:800]

        existing_msg = existing_messages.get(c["url"], "")

        candidate_text += f"""
--- Candidate {i+1} ---
Name: {c['first_name']} {c['last_name']}
Position: {c['position']}
Company: {c['company']}
Email: {c['email'] or 'N/A'}
LinkedIn: {c['url']}
Enriched Profile: {enrichment or 'No additional data'}
Existing Message: {existing_msg or 'None — write a new one'}
"""

    prompt = f"""You are helping {cfg['client_name']} find relevant people in their LinkedIn network.

{cfg['client_name']}'s query: "{query}"

CLIENT PROFILE:
- Ideal prospects: {cfg['q1_ideal_prospects']}
- Target industries & bonus signals: {cfg['q2_industries_and_signals']}
- Desired next step: {cfg['q4_cta']}

Here are the pre-filtered candidates from their network:
{candidate_text}

For each candidate, evaluate their relevance to the query and client profile. Then return a JSON array (no markdown fences) of the top candidates ranked by relevance. Each object should have:
- "name": full name
- "position": their job title
- "company": their company
- "email": their email or null
- "url": LinkedIn URL
- "relevance_score": 1-100 how relevant they are to the query
- "reason": 1-2 sentences explaining why they're relevant
- "message": If the candidate already has an "Existing Message" above, reuse it exactly. Only write a new personalized LinkedIn outreach message (2-3 sentences) for candidates with "None — write a new one". Voice/tone: {cfg['q3_voice']}. Start with "Hey [first name]", reference something specific about them, end with a CTA toward: {cfg['q4_cta']}

Only include candidates with relevance_score >= 30. Return valid JSON array only."""

    response = await client.messages.create(
        model=RANK_MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    text = re.sub(r"^```json?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        ranked = json.loads(text)
    except json.JSONDecodeError:
        print(f"Claude returned invalid JSON: {text[:200]}", file=sys.stderr)
        return []

    # Ensure existing messages are preserved even if Claude rewrote them
    for r in ranked:
        url = r.get("url", "")
        if url in existing_messages and existing_messages[url]:
            r["message"] = existing_messages[url]

    return ranked


# ── SSE helpers ──────────────────────────────────────────────────────────────

def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── API ──────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    query: str


class EnrichRequest(BaseModel):
    username: str
    raw_text: str


@app.post("/ask")
async def ask_network(req: AskRequest):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    async def event_stream():
        client = anthropic.AsyncAnthropic()
        cfg = load_config()

        print(f"\n{'='*60}")
        print(f"Query: {req.query}")
        print(f"{'='*60}")

        connections = load_connections()
        total = len(connections)
        print(f"Loaded {total} connections")

        yield sse_event("progress", {
            "stage": "prefilter",
            "batch": 0,
            "total": (total + PREFILTER_BATCH_SIZE - 1) // PREFILTER_BATCH_SIZE,
            "total_connections": total,
        })

        async def on_prefilter_progress(stage, completed, total_batches):
            pass  # Progress is sent after all batches complete

        candidates = await claude_prefilter(client, req.query, connections, cfg)
        num_candidates = len(candidates)
        print(f"Claude pre-filtered to {num_candidates} candidates")

        yield sse_event("progress", {
            "stage": "prefilter_done",
            "candidates": num_candidates,
            "total_connections": total,
        })

        if not candidates:
            yield sse_event("result", {
                "query": req.query,
                "total_connections": total,
                "prefiltered": 0,
                "results": [],
                "message": "No matches found in your network.",
            })
            yield sse_event("done", {})
            return

        yield sse_event("progress", {"stage": "enriching", "count": num_candidates})

        async def on_enrich_progress(enriched_so_far, total_to_enrich):
            pass  # SSE progress sent after enrichment completes

        enriched = await enrich_candidates(candidates, on_enrich_progress)
        cached_count = sum(1 for c in enriched if c.get("enrichment"))
        print(f"Enrichment: {cached_count} profiles enriched out of {num_candidates}")

        yield sse_event("progress", {
            "stage": "ranking",
            "candidates": min(num_candidates, MAX_TO_CLAUDE),
        })

        print("Deep ranking with Claude Sonnet...")
        ranked = await rank_with_claude(client, req.query, enriched)
        print(f"Returned {len(ranked)} ranked results")

        yield sse_event("result", {
            "query": req.query,
            "total_connections": total,
            "prefiltered": num_candidates,
            "results": ranked,
        })
        yield sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/enrich")
def enrich_profile(req: EnrichRequest):
    """Store enrichment data in cache. Called externally after scraping."""
    cache = load_cache()
    cache[req.username] = {"raw_text": req.raw_text, "username": req.username}
    save_cache(cache)
    return {"status": "cached", "username": req.username}


@app.get("/cache")
def get_cache():
    """View current enrichment cache."""
    cache = load_cache()
    return {"cached_profiles": len(cache), "usernames": list(cache.keys())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
