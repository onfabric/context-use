/**
 * Configuration validation and backend factory.
 */
import { z } from "zod";
import type { DatabaseBackend } from "./db/backend.js";
import type { StorageBackend } from "./storage/backend.js";

// ---------------------------------------------------------------------------
// Config schema
// ---------------------------------------------------------------------------

const StorageConfigSchema = z.object({
  provider: z.enum(["disk", "s3"]).default("disk"),
  config: z.record(z.any()).default({}),
});

const DbConfigSchema = z.object({
  provider: z.enum(["sqlite", "postgres"]).default("sqlite"),
  config: z.record(z.any()).default({}),
});

export const ConfigSchema = z.object({
  storage: StorageConfigSchema.default({}),
  db: DbConfigSchema.default({}),
});

export type Config = z.infer<typeof ConfigSchema>;

// ---------------------------------------------------------------------------
// Storage factories
// ---------------------------------------------------------------------------

function buildStorage(provider: string, config: Record<string, any>): StorageBackend {
  switch (provider) {
    case "disk": {
      const { DiskStorage } = require("./storage/disk.js");
      return new DiskStorage(config.basePath ?? config.base_path ?? "./data");
    }
    case "s3": {
      const { S3Storage } = require("./storage/s3.js");
      return new S3Storage(config);
    }
    default:
      throw new Error(`Unknown storage provider: ${provider}`);
  }
}

// ---------------------------------------------------------------------------
// DB factories
// ---------------------------------------------------------------------------

function buildDb(provider: string, config: Record<string, any>): DatabaseBackend {
  switch (provider) {
    case "sqlite": {
      const { SQLiteBackend } = require("./db/sqlite.js");
      return new SQLiteBackend(config.path ?? ":memory:");
    }
    case "postgres": {
      const { PostgresBackend } = require("./db/postgres.js");
      return new PostgresBackend(
        config.connectionString ?? config.connection_string ?? "",
      );
    }
    default:
      throw new Error(`Unknown db provider: ${provider}`);
  }
}

// ---------------------------------------------------------------------------
// Top-level config → backends
// ---------------------------------------------------------------------------

export function parseConfig(
  raw: Record<string, any>,
): { storage: StorageBackend; db: DatabaseBackend } {
  const config = ConfigSchema.parse(raw);
  const storage = buildStorage(config.storage.provider, config.storage.config);
  const db = buildDb(config.db.provider, config.db.config);
  return { storage, db };
}

