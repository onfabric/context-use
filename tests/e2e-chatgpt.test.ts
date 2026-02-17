/**
 * End-to-end test: ChatGPT zip → Thread rows in SQLite.
 */
import { describe, test, expect } from "bun:test";
import { Provider } from "../src/providers/registry.js";
import { makeCtx, writeChatGPTZip, makeTmpDir } from "./fixtures.js";

describe("E2E ChatGPT", () => {
  test("full flow", async () => {
    const dir = makeTmpDir();
    const ctx = await makeCtx(dir);
    const zipPath = writeChatGPTZip(dir);

    const result = await ctx.processArchive(Provider.ChatGPT, zipPath);

    // Should complete without errors
    expect(result.tasksCompleted).toBe(1);
    expect(result.tasksFailed).toBe(0);
    expect(result.threadsCreated).toBeGreaterThan(0);
    expect(result.errors).toHaveLength(0);

    // Verify DB state
    const archive = await ctx._db.queryOne<{
      status: string;
      provider: string;
    }>("SELECT * FROM archives WHERE id = ?", [result.archiveId]);
    expect(archive).not.toBeNull();
    expect(archive!.status).toBe("completed");
    expect(archive!.provider).toBe("chatgpt");

    const tasks = await ctx._db.query<{
      interaction_type: string;
      status: string;
      uploaded_count: number;
    }>("SELECT * FROM etl_tasks WHERE archive_id = ?", [result.archiveId]);
    expect(tasks).toHaveLength(1);
    expect(tasks[0].interaction_type).toBe("chatgpt_conversations");
    expect(tasks[0].status).toBe("completed");
    expect(tasks[0].uploaded_count).toBeGreaterThan(0);

    const threads = await ctx._db.query<{
      provider: string;
      interaction_type: string;
      preview: string;
      payload: string;
      unique_key: string;
    }>("SELECT * FROM threads");
    expect(threads).toHaveLength(result.threadsCreated);
    for (const thread of threads) {
      expect(thread.provider).toBe("chatgpt");
      expect(thread.interaction_type).toBe("chatgpt_conversations");
      expect(thread.preview).toBeTruthy();
      expect(thread.payload).toBeTruthy();
      expect(thread.unique_key).toBeTruthy();
    }
  });
});

