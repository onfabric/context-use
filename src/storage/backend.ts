/**
 * Abstract storage backend interface.
 */
import type { ReadableStream } from "node:stream/web";

export interface StorageBackend {
  /** Write data to the given key. */
  write(key: string, data: Uint8Array | string): Promise<void>;

  /** Read data from the given key. */
  read(key: string): Promise<Uint8Array>;

  /** Open a readable stream for the given key. */
  readStream(key: string): ReadableStream<Uint8Array>;

  /** List all keys with the given prefix. */
  list(prefix: string): Promise<string[]>;

  /** Check if the key exists. */
  exists(key: string): Promise<boolean>;

  /** Delete the given key. */
  delete(key: string): Promise<void>;
}

