#!/usr/bin/env node
/**
 * Pre-flight check — validates that everything is ready before running the pipeline.
 */

import { existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

const CSV_PATH = resolve(ROOT, "public", "Connections.csv");
const issues = [];

// Check 1: CSV exists
if (!existsSync(CSV_PATH)) {
  issues.push(
    "Connections.csv not found in app/public/\n" +
    "  → Download your LinkedIn data and place Connections.csv in app/public/"
  );
}

// Check 2: API key
if (!process.env.ANTHROPIC_API_KEY) {
  issues.push(
    "ANTHROPIC_API_KEY not set\n" +
    '  → Run: export ANTHROPIC_API_KEY="sk-ant-your-key-here"'
  );
}

// Check 3: node_modules
if (!existsSync(resolve(ROOT, "node_modules"))) {
  issues.push(
    "Dependencies not installed\n" +
    "  → Run: npm install"
  );
}

if (issues.length > 0) {
  console.log("\n  Setup Check — Issues Found:\n");
  issues.forEach((issue, i) => {
    console.log(`  ${i + 1}. ${issue}\n`);
  });
  process.exit(1);
} else {
  console.log("\n  All checks passed! Ready to run: npm run generate\n");
}
