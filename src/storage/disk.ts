/**
 * Local filesystem storage backend.
 */
import { mkdir, readdir, unlink, stat } from "node:fs/promises";
import { join, dirname, resolve } from "node:path";
import type { ReadableStream } from "node:stream/web";
import type { StorageBackend } from "./backend.js";

export class DiskStorage implements StorageBackend {
  private basePath: string;

  constructor(basePath: string) {
    this.basePath = resolve(basePath);
  }

  private resolve(key: string): string {
    return join(this.basePath, key);
  }

  async write(key: string, data: Uint8Array | string): Promise<void> {
    const fullPath = this.resolve(key);
    await mkdir(dirname(fullPath), { recursive: true });
    await Bun.write(fullPath, data);
  }

  async read(key: string): Promise<Uint8Array> {
    const file = Bun.file(this.resolve(key));
    const buf = await file.arrayBuffer();
    return new Uint8Array(buf);
  }

  readStream(key: string): ReadableStream<Uint8Array> {
    const file = Bun.file(this.resolve(key));
    return file.stream() as unknown as ReadableStream<Uint8Array>;
  }

  async list(prefix: string): Promise<string[]> {
    const prefixPath = this.resolve(prefix);
    try {
      const s = await stat(prefixPath);
      if (s.isFile()) return [prefix];
    } catch {
      return [];
    }

    const keys: string[] = [];
    const walk = async (dir: string): Promise<void> => {
      const entries = await readdir(dir, { withFileTypes: true });
      for (const entry of entries) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          await walk(full);
        } else if (entry.isFile()) {
          // Make key relative to basePath
          keys.push(full.slice(this.basePath.length + 1));
        }
      }
    };

    await walk(prefixPath);
    return keys.sort();
  }

  async exists(key: string): Promise<boolean> {
    const file = Bun.file(this.resolve(key));
    return file.exists();
  }

  async delete(key: string): Promise<void> {
    try {
      await unlink(this.resolve(key));
    } catch {
      // Ignore if not found
    }
  }
}

