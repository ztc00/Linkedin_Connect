# Prospect Intelligence — LinkedIn Connection Analyzer

This is an AI-powered tool that scores your LinkedIn connections and generates personalized outreach messages for your top prospects.

## Onboarding (for new users)

When a user first opens this project, **immediately guide them through these 4 steps in order**. Do not skip any step. Be friendly, concise, and direct.

### Step 1: Get their LinkedIn Connections CSV

Ask the user:
> "To get started, I need your LinkedIn connections data. Here's how to get it (takes 2 minutes):
>
> 1. Go to linkedin.com → Settings & Privacy → Data Privacy → Get a copy of your data
> 2. Select 'Download larger data archive' and request it
> 3. When the email arrives (usually 10-30 min), download the zip and find `Connections.csv` inside
>
> Once you have the file, drop `Connections.csv` into the `app/public/` folder and let me know."

Wait for them to confirm the file is in place. Verify it exists at `app/public/Connections.csv` before proceeding.

### Step 2: Configure their client profile

Ask the user these 4 questions **one at a time**, waiting for each answer before asking the next:

1. "What job titles represent your ideal prospect – the people who could actually hire you or buy from you?"
2. "What industries or types of companies do you want to target? And is there anything specific that would make someone extra interesting to you?"
3. "How would you describe your own communication voice? I'll write every outreach message to sound exactly like you."
4. "What do you want to happen after someone reads your message – what's the ideal next step or call to action?"

Once all 4 are answered, write their answers to `client_config.json` in the project root:
```json
{
  "client_name": "Their Name",
  "q1_ideal_prospects": "their answer to Q1",
  "q2_industries_and_signals": "their answer to Q2",
  "q3_voice": "their answer to Q3",
  "q4_cta": "their answer to Q4"
}
```

### Step 3: Set up their Claude API key

Ask the user:
> "Now I need a Claude API key to score your connections. If you don't have one:
>
> 1. Go to console.anthropic.com
> 2. Sign up or log in → API Keys → Create Key
> 3. Copy the key (starts with `sk-ant-...`)
>
> Then run this in your terminal:
> ```
> export ANTHROPIC_API_KEY="your-key-here"
> ```
> Let me know when it's set."

Verify the key is set by checking the environment variable before proceeding.

### Step 4: Run setup and pipeline

Once all prerequisites are confirmed, run the setup script which installs everything:

**Mac/Linux:**
```bash
chmod +x setup.sh && ./setup.sh
```

**Windows (Command Prompt or PowerShell):**
```cmd
setup.bat
```

This installs frontend (npm) and backend (pip) dependencies, validates the CSV and API key.

Then run the scoring pipeline:
```bash
cd app && npm run generate && cd ..
```

This will:
- Parse their LinkedIn connections
- Score ALL connections via Claude AI across 5 dimensions (Authority, Scale, Proximity, Warmth, Activity) — each 0-20, total 100, calibrated to their specific goals
- Generate personalized outreach messages for the top 30 prospects in their voice
- Save results to `app/public/prospects.json`

After the pipeline completes, start both servers:

Terminal 1 — frontend:
```bash
cd app && npm run dev
```

Terminal 2 — backend (Mac/Linux):
```bash
source .venv/bin/activate
export ANTHROPIC_API_KEY="their-key"
python3 backend.py
```

Terminal 2 — backend (Windows):
```cmd
.venv\Scripts\activate
set ANTHROPIC_API_KEY=their-key
python backend.py
```

Terminal 3 — enrichment service (optional, enables live LinkedIn profile fetching):

Mac/Linux: `source .venv/bin/activate && python3 enrichment_service.py`
Windows: `.venv\Scripts\activate && python enrichment_service.py`

Then tell the user their dashboard is ready. The "Ranked List" tab shows pre-scored prospects, and the "Ask My Network" tab lets them search with natural language. If the enrichment service is running, searches will automatically fetch LinkedIn profiles for candidates.

## Project Structure

```
├── client_config.json         ← Client profile (goals, voice, CTA)
├── Connections.csv            ← Client's LinkedIn data (not committed)
├── backend.py                 ← FastAPI backend for "Ask My Network"
├── enrichment_service.py      ← LinkedIn MCP bridge (live profile fetching)
├── enrichment_cache.json      ← Cached LinkedIn enrichment data
├── setup.sh                   ← Setup script (Mac/Linux)
├── setup.bat                  ← Setup script (Windows)
├── app/
│   ├── public/
│   │   ├── Connections.csv    ← Copy of CSV for generate.js
│   │   └── prospects.json     ← Generated output (not committed)
│   ├── scripts/
│   │   └── generate.js        ← Claude API scoring pipeline (reads client_config.json)
│   ├── src/
│   │   ├── App.jsx            ← Main app with tab bar (Ranked List / Ask My Network)
│   │   ├── utils.js           ← Scoring helpers, tier logic
│   │   ├── index.css          ← Apple light mode design system
│   │   └── components/
│   │       ├── ProspectList.jsx
│   │       ├── ProspectRow.jsx
│   │       ├── ProspectModal.jsx
│   │       ├── AskNetwork.jsx  ← "Ask My Network" search (SSE streaming)
│   │       ├── TierBadge.jsx
│   │       └── ScoreBar.jsx
│   ├── package.json
│   └── CLAUDE.md              ← This file
```

## How "Ask My Network" Works (3-Stage AI Pipeline)

The search pipeline uses Claude AI at every stage — no dumb keyword matching:

1. **Claude Pre-Filter (Haiku, batched)** — sends ALL connections to `claude-haiku-4-5` in batches of 100. Claude intelligently identifies candidates that might match the query, reasoning about company names, languages, industries, and context. Runs 3 batches concurrently.

2. **LinkedIn Enrichment** — for each candidate, checks the cache first. If not cached, calls the enrichment bridge service (`enrichment_service.py` on port 8001) which uses Claude Code's LinkedIn MCP tools to fetch their full LinkedIn profile. Results are cached in `enrichment_cache.json` for future searches. If the enrichment service isn't running, gracefully falls back to cache-only.

3. **Claude Deep Rank (Sonnet)** — sends the pre-filtered candidates (up to 50) to `claude-sonnet-4-6` for final ranking, relevance scoring, and personalized outreach message generation.

Progress is streamed to the frontend via **Server-Sent Events (SSE)** so users see real-time stage updates.

## How the Enrichment Queue Works

The enrichment service (`enrichment_service.py`, port 8001) acts as a bridge between the backend and Claude Code's LinkedIn MCP tools.

**When a search runs:**
1. Backend identifies uncached candidates and POSTs their usernames to `/wait-for-enrichment`
2. The enrichment service adds them to an in-memory queue
3. Backend polls `/fetch/{username}` every 3 seconds (up to 2 minutes) waiting for results

**Claude Code processes the queue:**
While the enrichment service is running, Claude Code (with LinkedIn MCP access) should process the queue:
1. Check `GET /queue` — see pending usernames
2. Claim one with `POST /claim` — removes it from pending, marks as processing
3. Call `mcp__linkedin__get_person_profile` with the username
4. Submit the result to `POST /submit` with `{"username": "...", "raw_text": "..."}`
5. Repeat until queue is empty

**For any new client:** Start the enrichment service in Terminal 3, then have Claude Code run the enrichment processing loop while searches are happening. Results are cached in `enrichment_cache.json` so each profile only needs to be fetched once.

## How client_config.json drives the system

Both `generate.js` (batch scoring) and `backend.py` (Ask My Network) read from `client_config.json`:
- **q1_ideal_prospects** → determines Authority and Proximity scoring calibration
- **q2_industries_and_signals** → determines Scale scoring and warmth bonus signals
- **q3_voice** → shapes all outreach message tone and style
- **q4_cta** → sets the call-to-action in every message

To customize for a new client, just update `client_config.json` and re-run the pipeline.

## Scoring System (Ranked List tab)

Each connection is scored on 5 dimensions (0-20 each, 100 total):
- **Authority**: Seniority and decision-making power relative to client's goals
- **Scale**: Firm prestige relative to client's target companies
- **Proximity**: Role/industry relevance to client's goals
- **Warmth**: Personal connection signals (shared background, email, culture)
- **Activity**: Recency of connection

Tiers: HOT (≥50) | WARM UP (35-49) | COLD (<35)

## Tech Stack
- React 19 + Vite 8
- FastAPI + Python (async, SSE streaming)
- Anthropic Claude API (Haiku for AI pre-filtering, Sonnet for deep ranking)
- Pure CSS (no framework)
