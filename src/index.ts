/**
 * contextuse – configurable ETL library for processing data archives.
 */
import { unzipSync } from "fflate";
import { readFileSync } from "node:fs";
import { posix } from "node:path";

import { parseConfig } from "./config.js";
import { ETLPipeline, UploadStrategy } from "./core/etl.js";
import {
  ArchiveProcessingError,
  UnsupportedProviderError,
} from "./core/exceptions.js";
import type { PipelineResult, TaskMetadata } from "./core/types.js";
import type { DatabaseBackend } from "./db/backend.js";
import type { StorageBackend } from "./storage/backend.js";
import { PROVIDER_REGISTRY, getProviderConfig } from "./providers/registry.js";

export { Provider } from "./providers/registry.js";

export class ContextUse {
  private storage: StorageBackend;
  private db: DatabaseBackend;

  constructor(storage: StorageBackend, db: DatabaseBackend) {
    this.storage = storage;
    this.db = db;
  }

  /** Construct from a configuration dict (validates with Zod). */
  static async fromConfig(config: Record<string, any>): Promise<ContextUse> {
    const { storage, db } = parseConfig(config);
    const ctx = new ContextUse(storage, db);
    await ctx.db.initialize();
    return ctx;
  }

  /** Initialise the database (create tables). Call once after construction. */
  async initialize(): Promise<void> {
    await this.db.initialize();
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  async processArchive(
    provider: string,
    path: string,
  ): Promise<PipelineResult> {
    if (!(provider in PROVIDER_REGISTRY)) {
      throw new UnsupportedProviderError(
        `Unsupported provider: ${provider}`,
      );
    }

    const providerCfg = getProviderConfig(provider);

    // 1. Create Archive record
    const archiveId = crypto.randomUUID();
    const now = new Date().toISOString();
    await this.db.execute(
      `INSERT INTO archives (id, provider, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)`,
      [archiveId, provider, "created", now, now],
    );

    const result: PipelineResult = {
      archiveId,
      tasksCompleted: 0,
      tasksFailed: 0,
      threadsCreated: 0,
      errors: [],
    };

    try {
      // 2. Unzip into storage
      await this.unzip(path, `${archiveId}/`);

      // 3. Discover files & tasks
      const files = await this.storage.list(archiveId);
      const orchestrator = new providerCfg.orchestration();
      const taskDescriptors = orchestrator.discoverTasks(archiveId, files);

      // 4. Run ETL for each task
      for (const desc of taskDescriptors) {
        const interactionType = desc.interactionType;
        const filenames = desc.filenames;

        const itCfg = providerCfg.interactionTypes[interactionType];
        if (!itCfg) continue;

        const etlTaskId = crypto.randomUUID();
        const taskNow = new Date().toISOString();
        await this.db.execute(
          `INSERT INTO etl_tasks (id, archive_id, provider, interaction_type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)`,
          [etlTaskId, archiveId, provider, interactionType, "created", taskNow, taskNow],
        );

        const taskMeta: TaskMetadata = {
          archiveId,
          etlTaskId,
          provider,
          interactionType,
          filenames,
        };

        try {
          const pipeline = new ETLPipeline({
            extraction: new itCfg.extraction(),
            transform: new itCfg.transform(),
            upload: new UploadStrategy(),
            storage: this.storage,
            db: this.db,
          });

          // Update status: extracting
          await this.updateEtlTaskStatus(etlTaskId, "extracting");
          const raw = await pipeline.extract(taskMeta);

          // Update status: transforming
          await this.updateEtlTaskStatus(etlTaskId, "transforming");
          const threadBatches = await pipeline.transform(taskMeta, raw);

          // Update status: uploading
          await this.updateEtlTaskStatus(etlTaskId, "uploading");
          const count = await pipeline.upload(taskMeta, threadBatches);

          // Mark completed
          const extractedCount = raw.reduce((s, b) => s + b.length, 0);
          const transformedCount = threadBatches.reduce(
            (s, b) => s + b.length,
            0,
          );
          await this.db.execute(
            `UPDATE etl_tasks SET status = ?, extracted_count = ?, transformed_count = ?, uploaded_count = ?, updated_at = ? WHERE id = ?`,
            ["completed", extractedCount, transformedCount, count, new Date().toISOString(), etlTaskId],
          );

          result.tasksCompleted++;
          result.threadsCreated += count;
        } catch (exc: any) {
          await this.updateEtlTaskStatus(etlTaskId, "failed");
          result.tasksFailed++;
          result.errors.push(String(exc));
        }
      }

      // 5. Mark archive completed or failed
      const finalStatus =
        result.tasksFailed === 0 ? "completed" : "failed";
      await this.db.execute(
        `UPDATE archives SET status = ?, updated_at = ? WHERE id = ?`,
        [finalStatus, new Date().toISOString(), archiveId],
      );
    } catch (exc: any) {
      await this.db.execute(
        `UPDATE archives SET status = ?, updated_at = ? WHERE id = ?`,
        ["failed", new Date().toISOString(), archiveId],
      );
      throw new ArchiveProcessingError(String(exc));
    }

    return result;
  }

  // ------------------------------------------------------------------
  // Internals
  // ------------------------------------------------------------------

  /** Extract a zip archive into storage under `prefix`. */
  private async unzip(zipPath: string, prefix: string): Promise<void> {
    const zipData = readFileSync(zipPath);
    const files = unzipSync(new Uint8Array(zipData));

    for (const [name, data] of Object.entries(files)) {
      // Skip directories (empty data with trailing /)
      if (name.endsWith("/") && data.length === 0) continue;
      const normalised = posix.normalize(name);
      const key = `${prefix}${normalised}`;
      await this.storage.write(key, data);
    }
  }

  private async updateEtlTaskStatus(
    etlTaskId: string,
    status: string,
  ): Promise<void> {
    await this.db.execute(
      `UPDATE etl_tasks SET status = ?, updated_at = ? WHERE id = ?`,
      [status, new Date().toISOString(), etlTaskId],
    );
  }

  // Expose for tests
  get _db(): DatabaseBackend {
    return this.db;
  }
  get _storage(): StorageBackend {
    return this.storage;
  }
}

