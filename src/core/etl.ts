/**
 * ETL pipeline core – strategy interfaces and the async ETLPipeline runner.
 */
import type { DatabaseBackend } from "../db/backend.js";
import type { StorageBackend } from "../storage/backend.js";
import type { TaskMetadata, TaskDescriptor, ThreadRow } from "./types.js";
import {
  ExtractionFailedException,
  TransformFailedException,
  UploadFailedException,
} from "./exceptions.js";

// ---------------------------------------------------------------------------
// Strategy interfaces
// ---------------------------------------------------------------------------

/**
 * Decides which ETL tasks to create based on discovered files.
 *
 * Sub-classes set `MANIFEST_MAP`: a dict mapping relative file paths
 * (inside the extracted archive) to interaction-type strings.
 */
export abstract class OrchestrationStrategy {
  abstract readonly MANIFEST_MAP: Record<string, string>;

  discoverTasks(archiveId: string, files: string[]): TaskDescriptor[] {
    const tasks: TaskDescriptor[] = [];
    const prefix = `${archiveId}/`;

    for (const [pattern, interactionType] of Object.entries(this.MANIFEST_MAP)) {
      const expected = `${prefix}${pattern}`;
      const matching = files.filter((f) => f === expected);
      if (matching.length > 0) {
        tasks.push({ interactionType, filenames: matching });
      }
    }

    return tasks;
  }
}

/**
 * Reads raw provider data from storage and yields arrays of raw parsed records.
 */
export interface ExtractionStrategy {
  extract(
    task: TaskMetadata,
    storage: StorageBackend,
  ): Promise<Record<string, any>[][]>;
}

/**
 * Receives raw record batches from extract, builds thread-shaped rows
 * with ActivityStreams payloads.
 */
export interface TransformStrategy {
  transform(
    task: TaskMetadata,
    batches: Record<string, any>[][],
  ): Promise<ThreadRow[][]>;
}

// ---------------------------------------------------------------------------
// Upload strategy – raw SQL INSERT
// ---------------------------------------------------------------------------

export class UploadStrategy {
  async upload(
    task: TaskMetadata,
    batches: ThreadRow[][],
    db: DatabaseBackend,
  ): Promise<number> {
    let total = 0;

    await db.transaction(async () => {
      for (const batch of batches) {
        for (const row of batch) {
          const id = crypto.randomUUID();
          const now = new Date().toISOString();
          await db.execute(
            `INSERT INTO threads (id, unique_key, tapestry_id, etl_task_id, provider, interaction_type, preview, payload, asset_uri, source, version, asat, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [
              id,
              row.uniqueKey,
              task.tapestryId ?? null,
              task.etlTaskId,
              row.provider,
              row.interactionType,
              row.preview,
              JSON.stringify(row.payload),
              row.assetUri ?? null,
              row.source ?? null,
              row.version,
              row.asat.toISOString(),
              now,
              now,
            ],
          );
          total++;
        }
      }
    });

    return total;
  }
}

// ---------------------------------------------------------------------------
// Pipeline runner
// ---------------------------------------------------------------------------

export class ETLPipeline {
  private extraction: ExtractionStrategy;
  private transformStrategy: TransformStrategy;
  private uploadStrategy: UploadStrategy;
  private storage: StorageBackend | null;
  private db: DatabaseBackend | null;

  constructor(opts: {
    extraction: ExtractionStrategy;
    transform: TransformStrategy;
    upload?: UploadStrategy;
    storage?: StorageBackend;
    db?: DatabaseBackend;
  }) {
    this.extraction = opts.extraction;
    this.transformStrategy = opts.transform;
    this.uploadStrategy = opts.upload ?? new UploadStrategy();
    this.storage = opts.storage ?? null;
    this.db = opts.db ?? null;
  }

  /** Step 1: Extract raw records from provider data. */
  async extract(task: TaskMetadata): Promise<Record<string, any>[][]> {
    if (!this.storage) throw new Error("Storage backend not configured");
    try {
      return await this.extraction.extract(task, this.storage);
    } catch (err) {
      throw new ExtractionFailedException(String(err));
    }
  }

  /** Step 2: Transform raw records into thread-shaped rows. */
  async transform(
    task: TaskMetadata,
    batches: Record<string, any>[][],
  ): Promise<ThreadRow[][]> {
    try {
      return await this.transformStrategy.transform(task, batches);
    } catch (err) {
      throw new TransformFailedException(String(err));
    }
  }

  /** Step 3: Upload thread records to the database. */
  async upload(task: TaskMetadata, batches: ThreadRow[][]): Promise<number> {
    if (!this.db) throw new Error("Database backend not configured");
    try {
      return await this.uploadStrategy.upload(task, batches, this.db);
    } catch (err) {
      throw new UploadFailedException(String(err));
    }
  }

  /** Run the full extract → transform → upload pipeline. */
  async run(task: TaskMetadata): Promise<number> {
    const rawBatches = await this.extract(task);
    const threadBatches = await this.transform(task, rawBatches);
    const count = await this.upload(task, threadBatches);
    return count;
  }
}

