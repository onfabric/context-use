/**
 * Tests for ChatGPT transform strategy.
 */
import { describe, test, expect } from "bun:test";
import { join } from "node:path";
import {
  ChatGPTConversationsExtractionStrategy,
  ChatGPTConversationsTransformStrategy,
} from "../src/providers/chatgpt/conversations.js";
import { DiskStorage } from "../src/storage/disk.js";
import type { TaskMetadata } from "../src/core/types.js";
import { CHATGPT_CONVERSATIONS, makeTmpDir } from "./fixtures.js";

async function getChatGPTRawBatches() {
  const dir = makeTmpDir();
  const storage = new DiskStorage(join(dir, "store"));
  const key = "archive/conversations.json";
  await storage.write(key, JSON.stringify(CHATGPT_CONVERSATIONS));

  const extraction = new ChatGPTConversationsExtractionStrategy();
  const task: TaskMetadata = {
    archiveId: "a1",
    etlTaskId: "t1",
    provider: "chatgpt",
    interactionType: "chatgpt_conversations",
    filenames: [key],
  };
  const raw = await extraction.extract(task, storage);
  return { raw, task };
}

describe("ChatGPTTransform", () => {
  test("produces thread columns", async () => {
    const { raw, task } = await getChatGPTRawBatches();
    const transform = new ChatGPTConversationsTransformStrategy();
    const result = await transform.transform(task, raw);

    expect(result.length).toBeGreaterThanOrEqual(1);
    const first = result[0][0];
    expect(first).toHaveProperty("uniqueKey");
    expect(first).toHaveProperty("provider");
    expect(first).toHaveProperty("interactionType");
    expect(first).toHaveProperty("preview");
    expect(first).toHaveProperty("payload");
    expect(first).toHaveProperty("version");
    expect(first).toHaveProperty("asat");
    expect(first).toHaveProperty("assetUri");
  });

  test("payload is dict with fibre_kind", async () => {
    const { raw, task } = await getChatGPTRawBatches();
    const transform = new ChatGPTConversationsTransformStrategy();
    const result = await transform.transform(task, raw);

    for (const batch of result) {
      for (const row of batch) {
        expect(typeof row.payload).toBe("object");
        expect(row.payload).toHaveProperty("fibre_kind");
      }
    }
  });

  test("send and receive", async () => {
    const { raw, task } = await getChatGPTRawBatches();
    const transform = new ChatGPTConversationsTransformStrategy();
    const result = await transform.transform(task, raw);
    const allRows = result.flat();
    const kinds = allRows.map((r) => r.payload.fibre_kind);
    expect(kinds).toContain("SendMessage");
    expect(kinds).toContain("ReceiveMessage");
  });

  test("previews non-empty", async () => {
    const { raw, task } = await getChatGPTRawBatches();
    const transform = new ChatGPTConversationsTransformStrategy();
    const result = await transform.transform(task, raw);
    const allRows = result.flat();
    for (const row of allRows) {
      expect(row.preview).toBeTruthy();
    }
  });
});

