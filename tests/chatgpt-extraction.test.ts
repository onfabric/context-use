/**
 * Tests for ChatGPT extraction strategy.
 */
import { describe, test, expect } from "bun:test";
import { join } from "node:path";
import { ChatGPTConversationsExtractionStrategy } from "../src/providers/chatgpt/conversations.js";
import { DiskStorage } from "../src/storage/disk.js";
import type { TaskMetadata } from "../src/core/types.js";
import { CHATGPT_CONVERSATIONS, makeTmpDir } from "./fixtures.js";

function makeChatGPTStorage() {
  const dir = makeTmpDir();
  const storage = new DiskStorage(join(dir, "store"));
  const key = "archive/conversations.json";
  const data = JSON.stringify(CHATGPT_CONVERSATIONS);
  // Write synchronously via Bun
  storage.write(key, data);
  return { storage, key };
}

const makeTask = (key: string): TaskMetadata => ({
  archiveId: "a1",
  etlTaskId: "t1",
  provider: "chatgpt",
  interactionType: "chatgpt_conversations",
  filenames: [key],
});

describe("ChatGPTExtraction", () => {
  test("extracts correct columns", async () => {
    const { storage, key } = makeChatGPTStorage();
    // Wait for write to finish
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new ChatGPTConversationsExtractionStrategy();
    const task = makeTask(key);

    const batches = await strategy.extract(task, storage);
    expect(batches.length).toBeGreaterThanOrEqual(1);

    const first = batches[0];
    const cols = Object.keys(first[0]);
    expect(cols).toContain("role");
    expect(cols).toContain("content");
    expect(cols).toContain("create_time");
    expect(cols).toContain("conversation_id");
    expect(cols).toContain("conversation_title");
    expect(cols).toContain("source");
  });

  test("skips system messages", async () => {
    const { storage, key } = makeChatGPTStorage();
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new ChatGPTConversationsExtractionStrategy();
    const task = makeTask(key);

    const batches = await strategy.extract(task, storage);
    const allRows = batches.flat();
    const roles = allRows.map((r) => r.role);
    expect(roles).not.toContain("system");
  });

  test("row count", async () => {
    const { storage, key } = makeChatGPTStorage();
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new ChatGPTConversationsExtractionStrategy();
    const task = makeTask(key);

    const batches = await strategy.extract(task, storage);
    const total = batches.reduce((s, b) => s + b.length, 0);
    // conv-001: user + assistant (system skipped) = 2
    // conv-002: user + assistant + user = 3
    expect(total).toBe(5);
  });
});

