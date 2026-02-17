/**
 * End-to-end test: Instagram zip → Thread rows in SQLite.
 */
import { describe, test, expect } from "bun:test";
import { Provider } from "../src/providers/registry.js";
import { makeCtx, writeInstagramZip, makeTmpDir } from "./fixtures.js";

describe("E2E Instagram", () => {
  test("full flow", async () => {
    const dir = makeTmpDir();
    const ctx = await makeCtx(dir);
    const zipPath = writeInstagramZip(dir);

    const result = await ctx.processArchive(Provider.Instagram, zipPath);

    // Should complete both stories and reels tasks
    expect(result.tasksCompleted).toBe(2);
    expect(result.tasksFailed).toBe(0);
    expect(result.threadsCreated).toBeGreaterThan(0);
    expect(result.errors).toHaveLength(0);

    // Verify DB state
    const archive = await ctx._db.queryOne<{ status: string }>(
      "SELECT * FROM archives WHERE id = ?",
      [result.archiveId],
    );
    expect(archive).not.toBeNull();
    expect(archive!.status).toBe("completed");

    const tasks = await ctx._db.query<{
      interaction_type: string;
      status: string;
    }>("SELECT * FROM etl_tasks WHERE archive_id = ?", [result.archiveId]);
    const interactionTypes = new Set(tasks.map((t) => t.interaction_type));
    expect(interactionTypes.has("instagram_stories")).toBe(true);
    expect(interactionTypes.has("instagram_reels")).toBe(true);

    for (const t of tasks) {
      expect(t.status).toBe("completed");
    }

    const threads = await ctx._db.query<{
      interaction_type: string;
      asset_uri: string | null;
    }>("SELECT * FROM threads");
    expect(threads).toHaveLength(result.threadsCreated);

    const threadTypes = new Set(threads.map((t) => t.interaction_type));
    expect(threadTypes.has("instagram_stories")).toBe(true);
    expect(threadTypes.has("instagram_reels")).toBe(true);

    // All threads should have asset_uri
    for (const thread of threads) {
      expect(thread.asset_uri).not.toBeNull();
      expect(thread.asset_uri).toContain("media/");
    }
  });
});

