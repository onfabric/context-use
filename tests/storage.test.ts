/**
 * Unit tests for DiskStorage.
 */
import { describe, test, expect } from "bun:test";
import { DiskStorage } from "../src/storage/disk.js";
import { makeTmpDir } from "./fixtures.js";
import { join } from "node:path";

describe("DiskStorage", () => {
  test("write and read", async () => {
    const dir = makeTmpDir();
    const s = new DiskStorage(join(dir, "store"));
    await s.write("a/b.txt", "hello");
    const data = await s.read("a/b.txt");
    expect(new TextDecoder().decode(data)).toBe("hello");
  });

  test("exists", async () => {
    const dir = makeTmpDir();
    const s = new DiskStorage(join(dir, "store"));
    expect(await s.exists("missing.txt")).toBe(false);
    await s.write("found.txt", "here");
    expect(await s.exists("found.txt")).toBe(true);
  });

  test("list keys", async () => {
    const dir = makeTmpDir();
    const s = new DiskStorage(join(dir, "store"));
    await s.write("p/one.txt", "1");
    await s.write("p/two.txt", "2");
    await s.write("q/three.txt", "3");
    const keys = await s.list("p");
    expect(keys.sort()).toEqual(["p/one.txt", "p/two.txt"]);
  });

  test("list keys empty", async () => {
    const dir = makeTmpDir();
    const s = new DiskStorage(join(dir, "store"));
    const keys = await s.list("nope");
    expect(keys).toEqual([]);
  });

  test("delete", async () => {
    const dir = makeTmpDir();
    const s = new DiskStorage(join(dir, "store"));
    await s.write("del.txt", "bye");
    expect(await s.exists("del.txt")).toBe(true);
    await s.delete("del.txt");
    expect(await s.exists("del.txt")).toBe(false);
  });

  test("readStream", async () => {
    const dir = makeTmpDir();
    const s = new DiskStorage(join(dir, "store"));
    await s.write("stream.txt", "streaming content");
    const stream = s.readStream("stream.txt");
    const reader = stream.getReader();
    const chunks: Uint8Array[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    const all = Buffer.concat(chunks);
    expect(all.toString()).toBe("streaming content");
  });
});

