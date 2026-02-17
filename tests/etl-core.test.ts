/**
 * Unit tests for ETL pipeline with mock strategies.
 */
import { describe, test, expect } from "bun:test";
import {
  ETLPipeline,
  OrchestrationStrategy,
  UploadStrategy,
  type ExtractionStrategy,
  type TransformStrategy,
} from "../src/core/etl.js";
import {
  ExtractionFailedException,
  TransformFailedException,
} from "../src/core/exceptions.js";
import type { TaskMetadata, ThreadRow } from "../src/core/types.js";
import { SQLiteBackend } from "../src/db/sqlite.js";
import { DiskStorage } from "../src/storage/disk.js";
import { makeTmpDir } from "./fixtures.js";
import { join } from "node:path";

class MockExtraction implements ExtractionStrategy {
  async extract(): Promise<Record<string, any>[][]> {
    return [
      [
        { role: "user", content: "hi" },
        { role: "assistant", content: "hello" },
      ],
    ];
  }
}

class MockTransform implements TransformStrategy {
  async transform(
    task: TaskMetadata,
    batches: Record<string, any>[][],
  ): Promise<ThreadRow[][]> {
    const rows: ThreadRow[] = [];
    for (const batch of batches) {
      for (const r of batch) {
        rows.push({
          uniqueKey: `mock:${r.content}`,
          provider: task.provider,
          interactionType: task.interactionType,
          preview: r.content,
          payload: { text: r.content },
          source: null,
          version: "1.0.0",
          asat: new Date(),
          assetUri: null,
        });
      }
    }
    return [rows];
  }
}

class FailingExtraction implements ExtractionStrategy {
  async extract(): Promise<Record<string, any>[][]> {
    throw new Error("boom");
  }
}

class FailingTransform implements TransformStrategy {
  async transform(): Promise<ThreadRow[][]> {
    throw new Error("kaboom");
  }
}

const task: TaskMetadata = {
  archiveId: "a1",
  etlTaskId: "t1",
  provider: "test",
  interactionType: "test_type",
  filenames: ["test.json"],
};

describe("ETLPipeline", () => {
  test("full run", async () => {
    const dir = makeTmpDir();
    const storage = new DiskStorage(join(dir, "s"));
    const db = new SQLiteBackend(":memory:");
    await db.initialize();

    // Create archive + etl_task so FK constraint is satisfied
    await db.execute(
      "INSERT INTO archives (id, provider, status) VALUES (?, ?, ?)",
      ["a1", "test", "created"],
    );
    await db.execute(
      "INSERT INTO etl_tasks (id, archive_id, provider, interaction_type, status) VALUES (?, ?, ?, ?, ?)",
      ["t1", "a1", "test", "test_type", "created"],
    );

    const pipeline = new ETLPipeline({
      extraction: new MockExtraction(),
      transform: new MockTransform(),
      upload: new UploadStrategy(),
      storage,
      db,
    });
    const count = await pipeline.run(task);
    expect(count).toBe(2);
    await db.close();
  });

  test("extract failure", async () => {
    const dir = makeTmpDir();
    const storage = new DiskStorage(join(dir, "s"));
    const db = new SQLiteBackend(":memory:");
    await db.initialize();

    const pipeline = new ETLPipeline({
      extraction: new FailingExtraction(),
      transform: new MockTransform(),
      storage,
      db,
    });
    expect(pipeline.run(task)).rejects.toThrow(ExtractionFailedException);
    await db.close();
  });

  test("transform failure", async () => {
    const dir = makeTmpDir();
    const storage = new DiskStorage(join(dir, "s"));
    const db = new SQLiteBackend(":memory:");
    await db.initialize();

    const pipeline = new ETLPipeline({
      extraction: new MockExtraction(),
      transform: new FailingTransform(),
      storage,
      db,
    });
    expect(pipeline.run(task)).rejects.toThrow(TransformFailedException);
    await db.close();
  });
});

describe("OrchestrationStrategy", () => {
  test("discover", () => {
    class TestOrch extends OrchestrationStrategy {
      readonly MANIFEST_MAP = { "data.json": "test_task" };
    }
    const orch = new TestOrch();
    const tasks = orch.discoverTasks("a1", ["a1/data.json", "a1/other.txt"]);
    expect(tasks).toHaveLength(1);
    expect(tasks[0].interactionType).toBe("test_task");
    expect(tasks[0].filenames).toEqual(["a1/data.json"]);
  });

  test("discover ignores suffix match", () => {
    class TestOrch extends OrchestrationStrategy {
      readonly MANIFEST_MAP = { "conversations.json": "chatgpt_conversations" };
    }
    const orch = new TestOrch();
    const tasks = orch.discoverTasks("a1", [
      "a1/conversations.json",
      "a1/shared_conversations.json",
    ]);
    expect(tasks).toHaveLength(1);
    expect(tasks[0].filenames).toEqual(["a1/conversations.json"]);
  });

  test("discover empty", () => {
    class TestOrch extends OrchestrationStrategy {
      readonly MANIFEST_MAP = { "data.json": "test_task" };
    }
    const orch = new TestOrch();
    const tasks = orch.discoverTasks("a1", ["a1/other.txt"]);
    expect(tasks).toEqual([]);
  });
});

