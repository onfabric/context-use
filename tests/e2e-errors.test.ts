/**
 * End-to-end error handling tests.
 */
import { describe, test, expect } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { ContextUse } from "../src/index.js";
import {
  ArchiveProcessingError,
  UnsupportedProviderError,
} from "../src/core/exceptions.js";
import { Provider } from "../src/providers/registry.js";
import { buildZip, makeCtx, makeTmpDir } from "./fixtures.js";

describe("E2E Errors", () => {
  test("bad zip", async () => {
    const dir = makeTmpDir();
    const ctx = await makeCtx(dir);
    const badPath = join(dir, "bad.zip");
    writeFileSync(badPath, "not a zip file");

    expect(
      ctx.processArchive(Provider.ChatGPT, badPath),
    ).rejects.toThrow(ArchiveProcessingError);
  });

  test("unsupported provider", async () => {
    const dir = makeTmpDir();
    const ctx = await makeCtx(dir);
    const dummyPath = join(dir, "dummy.zip");
    writeFileSync(dummyPath, buildZip({ "file.txt": "hello" }));

    expect(
      ctx.processArchive("unknown_provider", dummyPath),
    ).rejects.toThrow(UnsupportedProviderError);
  });

  test("empty archive", async () => {
    const dir = makeTmpDir();
    const ctx = await makeCtx(dir);
    const emptyPath = join(dir, "empty.zip");
    writeFileSync(emptyPath, buildZip({ "readme.txt": "nothing here" }));

    const result = await ctx.processArchive(Provider.ChatGPT, emptyPath);
    expect(result.tasksCompleted).toBe(0);
    expect(result.threadsCreated).toBe(0);
  });

  test("corrupt json", async () => {
    const dir = makeTmpDir();
    const ctx = await makeCtx(dir);
    const badJsonPath = join(dir, "bad_json.zip");
    writeFileSync(
      badJsonPath,
      buildZip({ "conversations.json": "{not valid json]]]" }),
    );

    const result = await ctx.processArchive(Provider.ChatGPT, badJsonPath);
    // The task should fail but the archive should complete (with errors)
    expect(result.tasksFailed).toBe(1);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});

