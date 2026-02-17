/**
 * Abstract database backend interface.
 *
 * All implementations use raw SQL — no ORM.
 */
export interface DatabaseBackend {
  /** Create tables / indexes from schema.sql. */
  initialize(): Promise<void>;

  /** Execute a write statement (INSERT, UPDATE, DELETE). */
  execute(sql: string, params?: any[]): Promise<void>;

  /** Run a SELECT and return all matching rows. */
  query<T = Record<string, any>>(sql: string, params?: any[]): Promise<T[]>;

  /** Run a SELECT and return the first row, or null. */
  queryOne<T = Record<string, any>>(
    sql: string,
    params?: any[],
  ): Promise<T | null>;

  /** Execute `fn` inside a transaction. */
  transaction<T>(fn: () => Promise<T>): Promise<T>;

  /** Close the connection / release resources. */
  close(): Promise<void>;
}

