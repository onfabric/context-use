#!/usr/bin/env bun
/**
 * CLI entrypoint for contextuse.
 *
 * Usage:
 *   bun run src/cli.ts --chatgpt ~/chatgpt.zip --instagram ~/instagram.zip
 *   ./contextuse --chatgpt ~/chatgpt.zip
 */
import { parseArgs } from "node:util";
import { ContextUse, Provider } from "./index.js";

const USAGE = `
contextuse — ETL for data archives

Usage:
  contextuse --chatgpt <path.zip>
  contextuse --instagram <path.zip>
  contextuse --chatgpt <c.zip> --instagram <i.zip>

Options:
  --chatgpt <path>       Path to ChatGPT export ZIP
  --instagram <path>     Path to Instagram export ZIP
  --storage-path <dir>   Storage directory  (default: ./data)
  --db-path <file>       SQLite database    (default: ./contextuse.db)
  --help                 Show this help
`.trim();

const { values } = parseArgs({
  args: Bun.argv.slice(2),
  options: {
    chatgpt: { type: "string" },
    instagram: { type: "string" },
    "storage-path": { type: "string", default: "./data" },
    "db-path": { type: "string", default: "./contextuse.db" },
    help: { type: "boolean", short: "h", default: false },
  },
  strict: true,
});

if (values.help) {
  console.log(USAGE);
  process.exit(0);
}

if (!values.chatgpt && !values.instagram) {
  console.error(USAGE);
  process.exit(1);
}

const ctx = await ContextUse.fromConfig({
  storage: {
    provider: "disk",
    config: { basePath: values["storage-path"] },
  },
  db: {
    provider: "sqlite",
    config: { path: values["db-path"] },
  },
});

if (values.chatgpt) {
  console.log(`Processing ChatGPT archive: ${values.chatgpt}`);
  const result = await ctx.processArchive(Provider.ChatGPT, values.chatgpt);
  console.log(
    `  ChatGPT: ${result.threadsCreated} threads from ${result.tasksCompleted} tasks`,
  );
  if (result.errors.length > 0) {
    console.log(`  Errors: ${JSON.stringify(result.errors)}`);
  }
}

if (values.instagram) {
  console.log(`\nProcessing Instagram archive: ${values.instagram}`);
  const result = await ctx.processArchive(
    Provider.Instagram,
    values.instagram,
  );
  console.log(
    `  Instagram: ${result.threadsCreated} threads from ${result.tasksCompleted} tasks`,
  );
  if (result.errors.length > 0) {
    console.log(`  Errors: ${JSON.stringify(result.errors)}`);
  }
}

console.log(
  `\nDone! Data stored in ${values["db-path"]} and ${values["storage-path"]}/`,
);

