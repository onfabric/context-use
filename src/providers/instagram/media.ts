/**
 * Instagram stories + reels extraction and transform strategies.
 */
import type { ExtractionStrategy, TransformStrategy } from "../../core/etl.js";
import type { TaskMetadata, ThreadRow } from "../../core/types.js";
import type { StorageBackend } from "../../storage/backend.js";
import {
  InstagramStoriesManifestSchema,
  InstagramReelsManifestSchema,
  type InstagramMediaItem,
} from "./schemas.js";
import {
  CURRENT_THREAD_PAYLOAD_VERSION,
  makeImage,
  makeVideo,
  makeCreateObject,
  getCreateObjectPreview,
  uniqueKeySuffix,
  toDict,
  type FibreCreateObject,
} from "../../payload/models.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function inferMediaType(uri: string): "Image" | "Video" {
  const lower = uri.toLowerCase();
  if (/\.(mp4|mov|avi|webm|srt)$/.test(lower)) return "Video";
  return "Image";
}

function itemsToRecords(
  items: InstagramMediaItem[],
  sourceFile: string,
): Record<string, any>[] {
  return items.map((item) => ({
    uri: item.uri,
    creation_timestamp: item.creation_timestamp,
    title: item.title,
    media_type: inferMediaType(item.uri),
    source: JSON.stringify({ file: sourceFile, uri: item.uri }),
  }));
}

// ---------------------------------------------------------------------------
// Stories Extraction
// ---------------------------------------------------------------------------

export class InstagramStoriesExtractionStrategy implements ExtractionStrategy {
  async extract(
    task: TaskMetadata,
    storage: StorageBackend,
  ): Promise<Record<string, any>[][]> {
    const key = task.filenames[0];
    const raw = await storage.read(key);
    const json = JSON.parse(new TextDecoder().decode(raw));
    const manifest = InstagramStoriesManifestSchema.parse(json);

    const records = itemsToRecords(manifest.ig_stories, key);
    if (records.length === 0) return [];
    return [records];
  }
}

// ---------------------------------------------------------------------------
// Reels Extraction
// ---------------------------------------------------------------------------

export class InstagramReelsExtractionStrategy implements ExtractionStrategy {
  async extract(
    task: TaskMetadata,
    storage: StorageBackend,
  ): Promise<Record<string, any>[][]> {
    const key = task.filenames[0];
    const raw = await storage.read(key);
    const json = JSON.parse(new TextDecoder().decode(raw));
    const manifest = InstagramReelsManifestSchema.parse(json);

    const allItems: InstagramMediaItem[] = [];
    for (const entry of manifest.ig_reels_media) {
      allItems.push(...entry.media);
    }

    const records = itemsToRecords(allItems, key);
    if (records.length === 0) return [];
    return [records];
  }
}

// ---------------------------------------------------------------------------
// Shared Transform
// ---------------------------------------------------------------------------

class InstagramMediaTransformStrategy implements TransformStrategy {
  async transform(
    task: TaskMetadata,
    batches: Record<string, any>[][],
  ): Promise<ThreadRow[][]> {
    const resultBatches: ThreadRow[][] = [];

    for (const batch of batches) {
      const rows: ThreadRow[] = [];
      for (const record of batch) {
        const payload = this.buildPayload(record, task.provider);
        if (!payload) continue;

        const ts = record.creation_timestamp as number;
        const asat = new Date(ts * 1000);

        const dict = toDict(payload);
        rows.push({
          uniqueKey: `${task.interactionType}:${uniqueKeySuffix(dict)}`,
          provider: task.provider,
          interactionType: task.interactionType,
          preview: getCreateObjectPreview(payload, task.provider),
          payload: dict,
          source: record.source ?? null,
          version: CURRENT_THREAD_PAYLOAD_VERSION,
          asat,
          assetUri: record.uri ?? null,
        });
      }
      if (rows.length > 0) resultBatches.push(rows);
    }

    return resultBatches;
  }

  private buildPayload(
    record: Record<string, any>,
    provider: string,
  ): FibreCreateObject | null {
    const mediaType = record.media_type as string;
    const uri = record.uri as string;
    const title = record.title as string;
    const ts = record.creation_timestamp as number;
    const published = new Date(ts * 1000).toISOString();

    let mediaObj;
    if (mediaType === "Video") {
      mediaObj = makeVideo({
        url: uri,
        name: title || undefined,
        published,
      });
    } else {
      mediaObj = makeImage({
        url: uri,
        name: title || undefined,
        published,
      });
    }

    return makeCreateObject({ object: mediaObj, published });
  }
}

export class InstagramStoriesTransformStrategy extends InstagramMediaTransformStrategy {}

export class InstagramReelsTransformStrategy extends InstagramMediaTransformStrategy {}

