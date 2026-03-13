#!/usr/bin/env node
/**
 * LinkedIn Prospect Intelligence — Claude-Powered Pipeline
 *
 * Reads Connections.csv, scores ALL connections via Claude API,
 * then generates personalized connection messages for the top 30.
 *
 * Usage:
 *   export ANTHROPIC_API_KEY="sk-ant-..."
 *   node scripts/generate.js
 */

import Anthropic from "@anthropic-ai/sdk";
import { readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const PROJECT_ROOT = resolve(ROOT, "..");

// ─── Config ───
const CSV_PATH = resolve(ROOT, "public", "Connections.csv");
const OUT_PATH = resolve(ROOT, "public", "prospects.json");
const CONFIG_PATH = resolve(PROJECT_ROOT, "client_config.json");
const BATCH_SIZE = 40;
const TOP_N_MESSAGES = 30;
const MODEL = "claude-haiku-4-5-20251001";

function loadConfig() {
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, "utf-8"));
  } catch {
    return {
      client_name: "User",
      q1_ideal_prospects: "",
      q2_industries_and_signals: "",
      q3_voice: "Professional but friendly. Direct and concise.",
      q4_cta: "Get on a call.",
    };
  }
}

// ─── CSV Parser ───
function parseCSV(raw) {
  const lines = raw.split("\n");

  // Find the header row (skip LinkedIn's preamble)
  let headerIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].toLowerCase().includes("first name")) {
      headerIdx = i;
      break;
    }
  }
  if (headerIdx === -1) throw new Error("Could not find CSV header row");

  const header = parseCSVLine(lines[headerIdx]).map((h) =>
    h.trim().toLowerCase().replace(/\s+/g, "_")
  );

  const connections = [];
  for (let i = headerIdx + 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const cols = parseCSVLine(line);
    const row = {};
    header.forEach((h, j) => (row[h] = (cols[j] || "").trim()));

    const firstName = row["first_name"] || "";
    const lastName = row["last_name"] || "";
    const name = `${firstName} ${lastName}`.trim();
    if (!name) continue;

    connections.push({
      name,
      first_name: firstName,
      last_name: lastName,
      title: row["position"] || "",
      company: row["company"] || "",
      email: row["email_address"] || "",
      location: row["location"] || "",
      connected_on: row["connected_on"] || "",
      url: row["url"] || "",
    });
  }
  return connections;
}

function parseCSVLine(line) {
  const result = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      inQuotes = !inQuotes;
    } else if (c === "," && !inQuotes) {
      result.push(current);
      current = "";
    } else {
      current += c;
    }
  }
  result.push(current);
  return result;
}

// ─── Claude Scoring ───
async function scoreConnections(client, connections, cfg) {
  const allScored = [];
  const totalBatches = Math.ceil(connections.length / BATCH_SIZE);

  for (let b = 0; b < totalBatches; b++) {
    const batch = connections.slice(b * BATCH_SIZE, (b + 1) * BATCH_SIZE);
    const batchNum = b + 1;
    process.stdout.write(
      `\r  Scoring batch ${batchNum}/${totalBatches} (${allScored.length + batch.length}/${connections.length})...`
    );

    const connectionsText = batch
      .map(
        (c, i) =>
          `[${i}] ${c.name} | ${c.title} | ${c.company} | ${c.email ? "has email" : "no email"} | Connected: ${c.connected_on}`
      )
      .join("\n");

    const resp = await client.messages.create({
      model: MODEL,
      max_tokens: 4096,
      messages: [
        {
          role: "user",
          content: `You are scoring LinkedIn connections for ${cfg.client_name}.

Client profile:
- Ideal prospects: ${cfg.q1_ideal_prospects}
- Target industries & signals: ${cfg.q2_industries_and_signals}

Score each connection on 5 dimensions (0-20 each, total 100):

**Authority** (0-20): How senior/influential is this person relative to the client's goals? Can they refer, hire, or open doors?
- Partner/MD/Director/VP/Head = 16-20
- Manager/Senior Associate/Recruiter = 10-15
- Associate/Consultant/Analyst = 5-9
- Intern/Student/Junior/Unknown = 0-4

**Scale** (0-20): How prestigious/large is their firm relative to the client's target companies?
- Top-tier firms in the client's target industry = 18-20
- Well-known firms in adjacent industries = 14-17
- Mid-tier or relevant firms = 9-13
- Small/unknown/unrelated firms = 0-8

**Proximity** (0-20): How relevant is their role/industry to the client's goals?
- Directly in target role/industry = 17-20
- Adjacent or related role/industry = 10-16
- Loosely connected = 5-9
- Unrelated = 0-4

**Warmth** (0-20): Personal connection signals (shared background, culture, email available, mutual context)?
- Strong personal connection signals + has email = 17-20
- Some personal signals OR has email = 10-16
- Recently connected (2025-2026) = 6-9
- No warmth signals = 0-5

**Activity** (0-20): How recent is the connection?
- Connected in 2026 = 16-20
- Connected in 2025 = 10-15
- Connected in 2024 = 5-9
- Connected 2023 or earlier = 0-4

Respond with ONLY a JSON array. Each element: [index, authority, scale, proximity, warmth, activity]

Connections:
${connectionsText}`,
        },
      ],
    });

    const text = resp.content[0].text;
    let scores;
    try {
      const jsonMatch = text.match(/\[[\s\S]*\]/);
      scores = JSON.parse(jsonMatch[0]);
    } catch {
      console.error(`\n  Warning: Failed to parse batch ${batchNum}, using zeros`);
      scores = batch.map((_, i) => [i, 0, 0, 0, 0, 0]);
    }

    for (const row of scores) {
      const [idx, authority, scale, proximity, warmth, activity] = row;
      if (idx >= 0 && idx < batch.length) {
        const c = { ...batch[idx] };
        c.breakdown = {
          authority: Math.min(20, Math.max(0, authority)),
          scale: Math.min(20, Math.max(0, scale)),
          proximity: Math.min(20, Math.max(0, proximity)),
          warmth: Math.min(20, Math.max(0, warmth)),
          activity: Math.min(20, Math.max(0, activity)),
        };
        c.score =
          c.breakdown.authority +
          c.breakdown.scale +
          c.breakdown.proximity +
          c.breakdown.warmth +
          c.breakdown.activity;
        allScored.push(c);
      }
    }

    // Small delay between batches to avoid rate limits
    if (b < totalBatches - 1) {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  console.log("\n  Scoring complete.");
  return allScored;
}

// ─── Claude Message Generation ───
async function generateMessages(client, topProspects, cfg) {
  console.log(`\n  Generating connection messages for top ${topProspects.length}...`);

  const prospectsText = topProspects
    .map(
      (p, i) =>
        `[${i}] ${p.name} | ${p.title} | ${p.company} | Score: ${p.score} | Email: ${p.email ? "yes" : "no"} | Connected: ${p.connected_on}`
    )
    .join("\n");

  const resp = await client.messages.create({
    model: MODEL,
    max_tokens: 8192,
    messages: [
      {
        role: "user",
        content: `Write personalized LinkedIn connection request messages for each person below.

**About the sender (${cfg.client_name}):**
- Goals: ${cfg.q1_ideal_prospects}
- Industries & signals: ${cfg.q2_industries_and_signals}
- Communication style: ${cfg.q3_voice}
- Never says: "I hope this finds you well", "I would be honored", "esteemed", "thriving"
- CTA: ${cfg.q4_cta}

**Rules:**
- 2-3 sentences max
- Reference something SPECIFIC about their role or company — not generic
- If there are shared background signals, briefly mention them
- Sound like a smart friend, not a vendor or applicant begging
- Vary the openings — don't start every message the same way

Respond with ONLY a JSON array of objects: [{"index": 0, "message": "..."}, ...]

Prospects:
${prospectsText}`,
      },
    ],
  });

  const text = resp.content[0].text;
  let messages;
  try {
    const jsonMatch = text.match(/\[[\s\S]*\]/);
    messages = JSON.parse(jsonMatch[0]);
  } catch {
    console.error("  Warning: Failed to parse messages response");
    return topProspects;
  }

  for (const m of messages) {
    if (m.index >= 0 && m.index < topProspects.length) {
      topProspects[m.index].message = m.message;
    }
  }
  console.log("  Messages generated.");
  return topProspects;
}

// ─── Main ───
async function main() {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error(
      "\n  Error: ANTHROPIC_API_KEY not set.\n  Run: export ANTHROPIC_API_KEY=\"sk-ant-...\"\n"
    );
    process.exit(1);
  }

  const client = new Anthropic();
  const cfg = loadConfig();

  console.log("\n  LinkedIn Prospect Intelligence Pipeline");
  console.log(`  Client: ${cfg.client_name}`);
  console.log("  ─────────────────────────────────────────\n");

  // Step 1: Parse CSV
  console.log("  Step 1: Parsing Connections.csv...");
  const raw = readFileSync(CSV_PATH, "utf-8");
  const connections = parseCSV(raw);
  console.log(`  Found ${connections.length} connections.\n`);

  // Step 2: Score all via Claude
  console.log("  Step 2: Scoring via Claude API...");
  const scored = await scoreConnections(client, connections, cfg);

  // Step 3: Sort and rank
  scored.sort((a, b) => b.score - a.score);
  scored.forEach((p, i) => {
    p.rank = i + 1;
    p.message = "";
  });
  console.log(`\n  Step 3: Ranked ${scored.length} prospects.`);
  console.log(
    `  Top score: ${scored[0]?.score} (${scored[0]?.name})`
  );
  console.log(
    `  Median score: ${scored[Math.floor(scored.length / 2)]?.score}`
  );

  // Step 4: Generate messages for top N
  console.log(`\n  Step 4: Writing messages for top ${TOP_N_MESSAGES}...`);
  const topN = scored.slice(0, TOP_N_MESSAGES);
  await generateMessages(client, topN, cfg);

  // Step 5: Write output
  const output = {
    generated_at: new Date().toISOString(),
    total_connections: connections.length,
    prospects_found: scored.length,
    prospects: scored,
  };

  writeFileSync(OUT_PATH, JSON.stringify(output, null, 2));
  console.log(`\n  Step 5: Saved to ${OUT_PATH}`);

  // Summary
  const hot = scored.filter((p) => p.score >= 50).length;
  const warm = scored.filter((p) => p.score >= 35 && p.score < 50).length;
  const cold = scored.filter((p) => p.score < 35).length;
  const withEmail = scored.filter((p) => p.email).length;
  const withMsg = scored.filter((p) => p.message).length;

  console.log(`\n  ─── Summary ───`);
  console.log(`  Total scored:    ${scored.length}`);
  console.log(`  HOT (>=50):      ${hot}`);
  console.log(`  WARM (35-49):    ${warm}`);
  console.log(`  COLD (<35):      ${cold}`);
  console.log(`  With email:      ${withEmail}`);
  console.log(`  With message:    ${withMsg}`);
  console.log(`\n  Done! Run 'npm run dev' to see your dashboard.\n`);
}

main().catch((err) => {
  console.error("\n  Pipeline failed:", err.message);
  process.exit(1);
});
