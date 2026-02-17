/**
 * Unit tests for SQLite backend + raw SQL model CRUD.
 */
import { describe, test, expect } from "bun:test";
import { SQLiteBackend } from "../src/db/sqlite.js";

async function makeDb(): Promise<SQLiteBackend> {
  const db = new SQLiteBackend(":memory:");
  await db.initialize();
  return db;
}

describe("SQLiteBackend", () => {
  test("initialize creates tables", async () => {
    const db = await makeDb();
    // Query sqlite_master for table names
    const tables = await db.query<{ name: string }>(
      "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
    );
    const names = tables.map((t) => t.name);
    expect(names).toContain("archives");
    expect(names).toContain("etl_tasks");
    expect(names).toContain("threads");
    await db.close();
  });

  test("archive CRUD", async () => {
    const db = await makeDb();
    const id = crypto.randomUUID();
    await db.execute(
      "INSERT INTO archives (id, provider, status) VALUES (?, ?, ?)",
      [id, "chatgpt", "created"],
    );
    const row = await db.queryOne<{ id: string; provider: string; status: string }>(
      "SELECT * FROM archives WHERE id = ?",
      [id],
    );
    expect(row).not.toBeNull();
    expect(row!.provider).toBe("chatgpt");
    expect(row!.status).toBe("created");
    await db.close();
  });

  test("etl_task CRUD", async () => {
    const db = await makeDb();
    const archiveId = crypto.randomUUID();
    await db.execute(
      "INSERT INTO archives (id, provider, status) VALUES (?, ?, ?)",
      [archiveId, "chatgpt", "created"],
    );

    const taskId = crypto.randomUUID();
    await db.execute(
      "INSERT INTO etl_tasks (id, archive_id, provider, interaction_type, status) VALUES (?, ?, ?, ?, ?)",
      [taskId, archiveId, "chatgpt", "chatgpt_conversations", "created"],
    );

    const row = await db.queryOne<{ id: string; interaction_type: string }>(
      "SELECT * FROM etl_tasks WHERE id = ?",
      [taskId],
    );
    expect(row).not.toBeNull();
    expect(row!.interaction_type).toBe("chatgpt_conversations");
    await db.close();
  });

  test("thread CRUD", async () => {
    const db = await makeDb();
    const id = crypto.randomUUID();
    await db.execute(
      `INSERT INTO threads (id, unique_key, provider, interaction_type, preview, payload, version, asat)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        id,
        "test:key",
        "chatgpt",
        "chatgpt_conversations",
        "hello",
        JSON.stringify({ type: "Create" }),
        "1.0.0",
        new Date().toISOString(),
      ],
    );

    const row = await db.queryOne<{
      id: string;
      unique_key: string;
      payload: string;
    }>("SELECT * FROM threads WHERE id = ?", [id]);
    expect(row).not.toBeNull();
    expect(row!.unique_key).toBe("test:key");
    expect(JSON.parse(row!.payload)).toEqual({ type: "Create" });
    await db.close();
  });

  test("transaction rollback", async () => {
    const db = await makeDb();
    const id = crypto.randomUUID();

    try {
      await db.transaction(async () => {
        await db.execute(
          "INSERT INTO archives (id, provider, status) VALUES (?, ?, ?)",
          [id, "chatgpt", "created"],
        );
        throw new Error("rollback test");
      });
    } catch {
      // expected
    }

    const row = await db.queryOne("SELECT * FROM archives WHERE id = ?", [id]);
    expect(row).toBeNull();
    await db.close();
  });
});

