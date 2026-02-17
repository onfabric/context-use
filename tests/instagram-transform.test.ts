/**
 * Tests for Instagram transform strategies.
 */
import { describe, test, expect } from "bun:test";
import { join } from "node:path";
import {
  InstagramStoriesExtractionStrategy,
  InstagramStoriesTransformStrategy,
  InstagramReelsExtractionStrategy,
  InstagramReelsTransformStrategy,
} from "../src/providers/instagram/media.js";
import { DiskStorage } from "../src/storage/disk.js";
import type { TaskMetadata } from "../src/core/types.js";
import {
  INSTAGRAM_STORIES_JSON,
  INSTAGRAM_REELS_JSON,
  makeTmpDir,
} from "./fixtures.js";

async function getIGStoriesRaw() {
  const dir = makeTmpDir();
  const storage = new DiskStorage(join(dir, "store"));
  const key = "archive/your_instagram_activity/media/stories.json";
  await storage.write(key, JSON.stringify(INSTAGRAM_STORIES_JSON));

  const ext = new InstagramStoriesExtractionStrategy();
  const task: TaskMetadata = {
    archiveId: "a1",
    etlTaskId: "t1",
    provider: "instagram",
    interactionType: "instagram_stories",
    filenames: [key],
  };
  const raw = await ext.extract(task, storage);
  return { raw, task };
}

async function getIGReelsRaw() {
  const dir = makeTmpDir();
  const storage = new DiskStorage(join(dir, "store"));
  const key = "archive/your_instagram_activity/media/reels.json";
  await storage.write(key, JSON.stringify(INSTAGRAM_REELS_JSON));

  const ext = new InstagramReelsExtractionStrategy();
  const task: TaskMetadata = {
    archiveId: "a1",
    etlTaskId: "t1",
    provider: "instagram",
    interactionType: "instagram_reels",
    filenames: [key],
  };
  const raw = await ext.extract(task, storage);
  return { raw, task };
}

describe("InstagramStoriesTransform", () => {
  test("produces thread columns", async () => {
    const { raw, task } = await getIGStoriesRaw();
    const transform = new InstagramStoriesTransformStrategy();
    const result = await transform.transform(task, raw);

    expect(result.length).toBeGreaterThanOrEqual(1);
    const first = result[0][0];
    expect(first).toHaveProperty("uniqueKey");
    expect(first).toHaveProperty("provider");
    expect(first).toHaveProperty("interactionType");
    expect(first).toHaveProperty("preview");
    expect(first).toHaveProperty("payload");
    expect(first).toHaveProperty("version");
    expect(first).toHaveProperty("asat");
    expect(first).toHaveProperty("assetUri");
  });

  test("payload is Create", async () => {
    const { raw, task } = await getIGStoriesRaw();
    const transform = new InstagramStoriesTransformStrategy();
    const result = await transform.transform(task, raw);

    for (const batch of result) {
      for (const row of batch) {
        expect(row.payload.fibre_kind).toBe("Create");
      }
    }
  });

  test("asset_uri populated", async () => {
    const { raw, task } = await getIGStoriesRaw();
    const transform = new InstagramStoriesTransformStrategy();
    const result = await transform.transform(task, raw);

    for (const batch of result) {
      for (const row of batch) {
        expect(row.assetUri).not.toBeNull();
        expect(row.assetUri).toContain("media/stories/");
      }
    }
  });
});

describe("InstagramReelsTransform", () => {
  test("reel transform", async () => {
    const { raw, task } = await getIGReelsRaw();
    const transform = new InstagramReelsTransformStrategy();
    const result = await transform.transform(task, raw);

    expect(result).toHaveLength(1);
    expect(result[0]).toHaveLength(1);
    expect(result[0][0].payload.fibre_kind).toBe("Create");
    // Reel is video
    expect(result[0][0].payload.object["@type"]).toBe("Video");
  });
});

