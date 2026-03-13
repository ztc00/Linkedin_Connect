"""
Ask My Network — FastAPI backend
POST /ask with {"query": "..."} → ranked enriched prospects + outreach messages

Enrichment strategy:
  1. Check enrichment_cache.json first (instant)
  2. If not cached, skip enrichment — Claude ranks on CSV data alone
  3. POST /enrich {"username": "..."} lets the frontend trigger on-demand enrichment
     (designed to be called from Claude Code's MCP tools or a separate scraper)
"""

import csv
import json
import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

MAX_PREFILTER = 20
MAX_TO_CLAUDE = 15


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


# ── Pre-filter ───────────────────────────────────────────────────────────────

SYNONYM_GROUPS = [
    {"founder", "co-founder", "cofounder", "fondateur", "co-fondateur", "cofondateur"},
    {"owner", "proprietor", "proprietaire", "propriétaire"},
    {"entrepreneur", "founder", "co-founder", "cofounder", "startup", "fondateur", "co-fondateur"},
    {"ceo", "chief executive", "directeur général", "directeur general", "pdg", "président", "president"},
    {"cto", "chief technology", "vp engineering", "head of engineering"},
    {"coo", "chief operating", "head of operations"},
    {"business", "entreprise", "commercial"},
    {"manager", "gestionnaire", "directeur", "director", "head"},
    {"marketing", "growth", "acquisition"},
    {"sales", "vente", "commercial", "account executive", "bdr", "sdr"},
    {"engineer", "developer", "développeur", "developpeur", "ingénieur", "ingenieur"},
    {"consultant", "advisor", "conseiller"},
    {"freelance", "freelancer", "independent", "indépendant", "independant", "self-employed"},
    {"small business", "sme", "pme", "startup", "start-up"},
]


def expand_synonyms(tokens: list[str]) -> set[str]:
    """Expand query tokens with synonyms so related terms match."""
    expanded = set(tokens)
    query_joined = " ".join(tokens)
    for group in SYNONYM_GROUPS:
        if any(term in query_joined for term in group) or any(t in group for t in tokens):
            expanded.update(group)
    return expanded


def prefilter(connections: list[dict], query: str) -> list[dict]:
    """Keyword match with synonym expansion. Returns up to MAX_PREFILTER."""
    tokens = [t.lower() for t in query.split() if len(t) > 2]
    expanded = expand_synonyms(tokens)
    scored = []
    for c in connections:
        searchable = f"{c['first_name']} {c['last_name']} {c['company']} {c['position']}".lower()
        hits = sum(1 for t in expanded if t in searchable)
        if hits > 0:
            scored.append((hits, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:MAX_PREFILTER]]


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


# ── Claude ranking ───────────────────────────────────────────────────────────

def rank_with_claude(query: str, candidates: list[dict]) -> list[dict]:
    """Send candidates to Claude for ranking + outreach messages."""
    client = anthropic.Anthropic()
    cfg = load_config()

    candidate_text = ""
    for i, c in enumerate(candidates[:MAX_TO_CLAUDE]):
        enrichment = ""
        if c.get("enrichment") and c["enrichment"].get("raw_text"):
            enrichment = c["enrichment"]["raw_text"][:800]

        candidate_text += f"""
--- Candidate {i+1} ---
Name: {c['first_name']} {c['last_name']}
Position: {c['position']}
Company: {c['company']}
Email: {c['email'] or 'N/A'}
LinkedIn: {c['url']}
Enriched Profile: {enrichment or 'No additional data'}
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
- "message": a personalized LinkedIn outreach message (2-3 sentences). Voice/tone: {cfg['q3_voice']}. Start with "Hey [first name]", reference something specific about them, end with a CTA toward: {cfg['q4_cta']}

Only include candidates with relevance_score >= 30. Return valid JSON array only."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    text = re.sub(r"^```json?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"Claude returned invalid JSON: {text[:200]}", file=sys.stderr)
        return []


# ── API ──────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    query: str


class EnrichRequest(BaseModel):
    username: str
    raw_text: str


@app.post("/ask")
def ask_network(req: AskRequest):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    print(f"\n{'='*60}")
    print(f"Query: {req.query}")
    print(f"{'='*60}")

    connections = load_connections()
    print(f"Loaded {len(connections)} connections")

    candidates = prefilter(connections, req.query)
    print(f"Pre-filtered to {len(candidates)} candidates")

    if not candidates:
        return {"query": req.query, "results": [], "message": "No matches found in your network."}

    # Attach cached enrichment (no scraping)
    enriched = attach_cached_enrichment(candidates)

    # Rank with Claude
    print("Ranking with Claude...")
    ranked = rank_with_claude(req.query, enriched)
    print(f"Returned {len(ranked)} ranked results")

    return {
        "query": req.query,
        "total_connections": len(connections),
        "prefiltered": len(candidates),
        "results": ranked,
    }


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
