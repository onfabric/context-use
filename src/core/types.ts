/**
 * ETL task metadata types.
 */

/** Metadata passed through every ETL pipeline step. */
export interface TaskMetadata {
  archiveId: string;
  etlTaskId: string;
  provider: string;
  interactionType: string;
  filenames: string[];
  tapestryId?: string;
}

/** Result returned from processArchive(). */
export interface PipelineResult {
  archiveId: string;
  tasksCompleted: number;
  tasksFailed: number;
  threadsCreated: number;
  errors: string[];
}

/** A single thread row ready for DB insertion. */
export interface ThreadRow {
  uniqueKey: string;
  provider: string;
  interactionType: string;
  preview: string;
  payload: Record<string, any>;
  source?: string | null;
  version: string;
  asat: Date;
  assetUri?: string | null;
}

/** A task descriptor discovered by orchestration. */
export interface TaskDescriptor {
  interactionType: string;
  filenames: string[];
}

