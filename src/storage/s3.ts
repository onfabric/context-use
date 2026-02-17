/**
 * S3-compatible storage backend using Bun's built-in S3 runtime.
 *
 * Works with AWS S3 and GCS (via GCS's S3-compatible XML API with HMAC keys).
 */
import { S3Client } from "bun";
import type { ReadableStream } from "node:stream/web";
import type { StorageBackend } from "./backend.js";

export interface S3StorageConfig {
  endpoint?: string;
  bucket: string;
  accessKeyId: string;
  secretAccessKey: string;
  region?: string;
  prefix?: string;
}

export class S3Storage implements StorageBackend {
  private client: S3Client;
  private prefix: string;

  constructor(config: S3StorageConfig) {
    this.client = new S3Client({
      endpoint: config.endpoint,
      bucket: config.bucket,
      accessKeyId: config.accessKeyId,
      secretAccessKey: config.secretAccessKey,
      region: config.region ?? "auto",
    });
    this.prefix = config.prefix ? config.prefix.replace(/\/$/, "") + "/" : "";
  }

  private fullKey(key: string): string {
    return `${this.prefix}${key}`;
  }

  async write(key: string, data: Uint8Array | string): Promise<void> {
    await this.client.write(this.fullKey(key), data);
  }

  async read(key: string): Promise<Uint8Array> {
    const file = this.client.file(this.fullKey(key));
    const buf = await file.arrayBuffer();
    return new Uint8Array(buf);
  }

  readStream(key: string): ReadableStream<Uint8Array> {
    const file = this.client.file(this.fullKey(key));
    return file.stream() as unknown as ReadableStream<Uint8Array>;
  }

  async list(prefix: string): Promise<string[]> {
    // Bun S3Client doesn't have a native list. Use presign/iterate approach.
    // For now, this is a best-effort implementation.
    // In practice, the unzip step writes known keys so listing may not be critical.
    throw new Error(
      "S3Storage.list() is not yet implemented. Track extracted keys during unzip instead.",
    );
  }

  async exists(key: string): Promise<boolean> {
    const file = this.client.file(this.fullKey(key));
    return await file.exists();
  }

  async delete(key: string): Promise<void> {
    const file = this.client.file(this.fullKey(key));
    await file.unlink();
  }
}

