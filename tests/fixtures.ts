/**
 * Shared test fixtures: mini JSON data, zip builder, pre-configured ctx.
 */
import { mkdtempSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { zipSync, strToU8 } from "fflate";

import { ContextUse } from "../src/index.js";
import { SQLiteBackend } from "../src/db/sqlite.js";
import { DiskStorage } from "../src/storage/disk.js";

// ---------------------------------------------------------------------------
// Mini ChatGPT conversations fixture
// ---------------------------------------------------------------------------

export const CHATGPT_CONVERSATIONS = [
  {
    title: "Hello World",
    conversation_id: "conv-001",
    mapping: {
      "msg-1": {
        message: {
          author: { role: "user" },
          content: { content_type: "text", parts: ["Hi there!"] },
          create_time: 1700000000.0,
        },
      },
      "msg-2": {
        message: {
          author: { role: "assistant" },
          content: {
            content_type: "text",
            parts: ["Hello! How can I help you?"],
          },
          create_time: 1700000001.0,
        },
      },
      "msg-3": {
        message: {
          author: { role: "system" },
          content: {
            content_type: "text",
            parts: ["You are a helpful assistant."],
          },
          create_time: 1700000002.0,
        },
      },
    },
  },
  {
    title: "Python Help",
    conversation_id: "conv-002",
    mapping: {
      "msg-4": {
        message: {
          author: { role: "user" },
          content: {
            content_type: "text",
            parts: ["How do I read a file in Python?"],
          },
          create_time: 1700001000.0,
        },
      },
      "msg-5": {
        message: {
          author: { role: "assistant" },
          content: {
            content_type: "text",
            parts: [
              "You can use open() to read a file. For example: with open('file.txt') as f: data = f.read()",
            ],
          },
          create_time: 1700001001.0,
        },
      },
      "msg-6": {
        message: {
          author: { role: "user" },
          content: {
            content_type: "text",
            parts: ["Thanks!"],
          },
          create_time: 1700001002.0,
        },
      },
    },
  },
];

// ---------------------------------------------------------------------------
// Mini Instagram fixtures
// ---------------------------------------------------------------------------

export const INSTAGRAM_STORIES_JSON = {
  ig_stories: [
    {
      uri: "media/stories/202512/story1.mp4",
      creation_timestamp: 1765390423,
      title: "",
      media_metadata: {
        video_metadata: { exif_data: [{}] },
      },
    },
    {
      uri: "media/stories/202512/story2.jpg",
      creation_timestamp: 1765390500,
      title: "My Day",
    },
  ],
};

export const INSTAGRAM_REELS_JSON = {
  ig_reels_media: [
    {
      media: [
        {
          uri: "media/reels/202506/reel1.mp4",
          creation_timestamp: 1750896174,
          title: "Fun Reel",
        },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// Zip builder helper
// ---------------------------------------------------------------------------

export function buildZip(files: Record<string, string | Uint8Array>): Uint8Array {
  const zipFiles: Record<string, Uint8Array> = {};
  for (const [name, data] of Object.entries(files)) {
    zipFiles[name] =
      typeof data === "string" ? strToU8(data) : data;
  }
  return zipSync(zipFiles);
}

// ---------------------------------------------------------------------------
// Temp dir + zip file helpers
// ---------------------------------------------------------------------------

export function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "contextuse-test-"));
}

export function writeChatGPTZip(dir: string): string {
  const data = buildZip({
    "conversations.json": JSON.stringify(CHATGPT_CONVERSATIONS),
  });
  const p = join(dir, "chatgpt-export.zip");
  writeFileSync(p, data);
  return p;
}

export function writeInstagramZip(dir: string): string {
  const data = buildZip({
    "your_instagram_activity/media/stories.json": JSON.stringify(
      INSTAGRAM_STORIES_JSON,
    ),
    "your_instagram_activity/media/reels.json": JSON.stringify(
      INSTAGRAM_REELS_JSON,
    ),
    "media/stories/202512/story1.mp4": new Uint8Array(10),
    "media/stories/202512/story2.jpg": new Uint8Array([0xff, 0xd8, 0xff, 0, 0, 0, 0, 0, 0, 0]),
    "media/reels/202506/reel1.mp4": new Uint8Array(10),
  });
  const p = join(dir, "instagram-export.zip");
  writeFileSync(p, data);
  return p;
}

// ---------------------------------------------------------------------------
// Pre-configured ContextUse
// ---------------------------------------------------------------------------

export async function makeCtx(dir: string): Promise<ContextUse> {
  const storage = new DiskStorage(join(dir, "storage"));
  const db = new SQLiteBackend(":memory:");
  const ctx = new ContextUse(storage, db);
  await ctx.initialize();
  return ctx;
}

