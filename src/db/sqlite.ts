/**
 * SQLite database backend using bun:sqlite.
 */
import { Database } from "bun:sqlite";
import type { DatabaseBackend } from "./backend.js";
import { SCHEMA_SQL } from "./schema.js";

export class SQLiteBackend implements DatabaseBackend {
  private db: Database;

  constructor(path: string = ":memory:") {
    this.db = new Database(path);
    this.db.exec("PRAGMA journal_mode = WAL;");
    this.db.exec("PRAGMA foreign_keys = ON;");
  }

  async initialize(): Promise<void> {
    this.db.exec(SCHEMA_SQL);
  }

  async execute(sql: string, params: any[] = []): Promise<void> {
    this.db.prepare(sql).run(...params);
  }

  async query<T = Record<string, any>>(
    sql: string,
    params: any[] = [],
  ): Promise<T[]> {
    return this.db.prepare(sql).all(...params) as T[];
  }

  async queryOne<T = Record<string, any>>(
    sql: string,
    params: any[] = [],
  ): Promise<T | null> {
    const row = this.db.prepare(sql).get(...params);
    return (row as T) ?? null;
  }

  async transaction<T>(fn: () => Promise<T>): Promise<T> {
    this.db.exec("BEGIN");
    try {
      const result = await fn();
      this.db.exec("COMMIT");
      return result;
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }

  async close(): Promise<void> {
    this.db.close();
  }
}
