/**
 * PostgreSQL database backend using postgres-js.
 *
 * This is an optional backend — `postgres` is in optionalDependencies.
 */
import type { DatabaseBackend } from "./backend.js";
import { SCHEMA_SQL } from "./schema.js";

export class PostgresBackend implements DatabaseBackend {
  private sql: any; // postgres.Sql

  constructor(connectionString: string) {
    // Dynamic import at construction to avoid hard dep
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const postgres = require("postgres");
      this.sql = postgres(connectionString);
    } catch {
      throw new Error(
        "postgres package is required for PostgresBackend. Install with: bun add postgres",
      );
    }
  }

  async initialize(): Promise<void> {
    await this.sql.unsafe(SCHEMA_SQL);
  }

  async execute(sql: string, params: any[] = []): Promise<void> {
    await this.sql.unsafe(sql, params);
  }

  async query<T = Record<string, any>>(
    sql: string,
    params: any[] = [],
  ): Promise<T[]> {
    const rows = await this.sql.unsafe(sql, params);
    return rows as T[];
  }

  async queryOne<T = Record<string, any>>(
    sql: string,
    params: any[] = [],
  ): Promise<T | null> {
    const rows = await this.sql.unsafe(sql, params);
    return (rows[0] as T) ?? null;
  }

  async transaction<T>(fn: () => Promise<T>): Promise<T> {
    return await this.sql.begin(async () => {
      return await fn();
    });
  }

  async close(): Promise<void> {
    await this.sql.end();
  }
}
