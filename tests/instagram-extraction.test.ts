/**
 * Tests for Instagram extraction strategies.
 */
import { describe, test, expect } from "bun:test";
import { join } from "node:path";
import {
  InstagramStoriesExtractionStrategy,
  InstagramReelsExtractionStrategy,
} from "../src/providers/instagram/media.js";
import { DiskStorage } from "../src/storage/disk.js";
import type { TaskMetadata } from "../src/core/types.js";
import {
  INSTAGRAM_STORIES_JSON,
  INSTAGRAM_REELS_JSON,
  makeTmpDir,
} from "./fixtures.js";

function makeIGStoriesStorage() {
  const dir = makeTmpDir();
  const storage = new DiskStorage(join(dir, "store"));
  const key = "archive/your_instagram_activity/media/stories.json";
  storage.write(key, JSON.stringify(INSTAGRAM_STORIES_JSON));
  return { storage, key };
}

function makeIGReelsStorage() {
  const dir = makeTmpDir();
  const storage = new DiskStorage(join(dir, "store"));
  const key = "archive/your_instagram_activity/media/reels.json";
  storage.write(key, JSON.stringify(INSTAGRAM_REELS_JSON));
  return { storage, key };
}

describe("InstagramStoriesExtraction", () => {
  test("extracts correct columns", async () => {
    const { storage, key } = makeIGStoriesStorage();
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new InstagramStoriesExtractionStrategy();
    const task: TaskMetadata = {
      archiveId: "a1",
      etlTaskId: "t1",
      provider: "instagram",
      interactionType: "instagram_stories",
      filenames: [key],
    };

    const batches = await strategy.extract(task, storage);
    expect(batches).toHaveLength(1);
    const cols = Object.keys(batches[0][0]);
    expect(cols).toContain("uri");
    expect(cols).toContain("creation_timestamp");
    expect(cols).toContain("title");
    expect(cols).toContain("media_type");
    expect(cols).toContain("source");
  });

  test("row count", async () => {
    const { storage, key } = makeIGStoriesStorage();
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new InstagramStoriesExtractionStrategy();
    const task: TaskMetadata = {
      archiveId: "a1",
      etlTaskId: "t1",
      provider: "instagram",
      interactionType: "instagram_stories",
      filenames: [key],
    };

    const batches = await strategy.extract(task, storage);
    expect(batches[0]).toHaveLength(2); // 2 stories in fixture
  });

  test("media type inference", async () => {
    const { storage, key } = makeIGStoriesStorage();
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new InstagramStoriesExtractionStrategy();
    const task: TaskMetadata = {
      archiveId: "a1",
      etlTaskId: "t1",
      provider: "instagram",
      interactionType: "instagram_stories",
      filenames: [key],
    };

    const batches = await strategy.extract(task, storage);
    const types = batches[0].map((r) => r.media_type);
    expect(types).toContain("Video"); // .mp4 file
    expect(types).toContain("Image"); // .jpg file
  });
});

describe("InstagramReelsExtraction", () => {
  test("extracts and flattens", async () => {
    const { storage, key } = makeIGReelsStorage();
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new InstagramReelsExtractionStrategy();
    const task: TaskMetadata = {
      archiveId: "a1",
      etlTaskId: "t1",
      provider: "instagram",
      interactionType: "instagram_reels",
      filenames: [key],
    };

    const batches = await strategy.extract(task, storage);
    expect(batches).toHaveLength(1);
    expect(batches[0]).toHaveLength(1); // 1 reel clip
  });

  test("reel is video", async () => {
    const { storage, key } = makeIGReelsStorage();
    await new Promise((r) => setTimeout(r, 50));
    const strategy = new InstagramReelsExtractionStrategy();
    const task: TaskMetadata = {
      archiveId: "a1",
      etlTaskId: "t1",
      provider: "instagram",
      interactionType: "instagram_reels",
      filenames: [key],
    };

    const batches = await strategy.extract(task, storage);
    expect(batches[0][0].media_type).toBe("Video");
  });
});

