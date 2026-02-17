/**
 * ActivityStreams 2.0 core + Fibre models (Zod-based).
 *
 * Self-contained, minimal copy covering the types used by
 * ChatGPT and Instagram providers.
 */
import { createHash } from "node:crypto";

// ---------------------------------------------------------------------------
// Current version
// ---------------------------------------------------------------------------

export const CURRENT_THREAD_PAYLOAD_VERSION = "1.0.0";

// ---------------------------------------------------------------------------
// Plain TypeScript types (mirror the Pydantic models)
// ---------------------------------------------------------------------------

export interface ASObject {
  "@type": string;
  "@id"?: string;
  attachment?: ASObject | ASObject[];
  attributedTo?: ASObject | ASObject[];
  content?: string | Record<string, string>;
  context?: ASObject | ASObject[];
  name?: string | Record<string, string>;
  endTime?: string;
  published?: string;
  startTime?: string;
  summary?: string | Record<string, string>;
  updated?: string;
  url?: string | string[];
  mediaType?: string;
  duration?: string;
  [key: string]: any;
}

export interface ASActivity extends ASObject {
  actor?: ASObject | ASObject[];
  object?: ASObject | ASObject[];
  target?: ASObject | ASObject[];
  result?: ASObject | ASObject[];
  origin?: ASObject | ASObject[];
  instrument?: ASObject | ASObject[];
}

// ---------------------------------------------------------------------------
// Concrete types used by providers
// ---------------------------------------------------------------------------

export interface Note extends ASObject {
  "@type": "Note";
}

export interface ImageType extends ASObject {
  "@type": "Image";
}

export interface VideoType extends ASObject {
  "@type": "Video";
}

export interface ProfileType extends ASObject {
  "@type": "Profile";
}

export interface ApplicationType extends ASObject {
  "@type": "Application";
}

export interface PersonType extends ASObject {
  "@type": "Person";
}

export interface CollectionType extends ASObject {
  "@type": "Collection";
  totalItems?: number;
  items?: ASObject[];
}

// ---------------------------------------------------------------------------
// Fibre types
// ---------------------------------------------------------------------------

export interface FibreTextMessage extends Note {
  fibre_kind: "TextMessage";
  context?: CollectionType;
}

export interface FibreImage extends ImageType {
  fibre_kind: "Image";
  context?: CollectionType;
}

export interface FibreVideo extends VideoType {
  fibre_kind: "Video";
  context?: CollectionType;
}

export interface FibreCollection extends CollectionType {
  fibre_kind: "Collection";
}

export interface FibreCreateObject extends ASActivity {
  "@type": "Create";
  fibre_kind: "Create";
  object: ImageType | VideoType;
  target?: FibreCollection;
}

export interface FibreSendMessage extends ASActivity {
  "@type": "Create";
  fibre_kind: "SendMessage";
  object: FibreTextMessage | FibreImage | FibreVideo;
  actor?: undefined;
  target: ProfileType | ApplicationType;
}

export interface FibreReceiveMessage extends ASActivity {
  "@type": "Create";
  fibre_kind: "ReceiveMessage";
  object: FibreTextMessage | FibreImage | FibreVideo;
  actor: ProfileType | ApplicationType;
  target?: undefined;
}

export type FibreByType =
  | FibreCreateObject
  | FibreImage
  | FibreVideo
  | FibreCollection
  | FibreSendMessage
  | FibreReceiveMessage;

export type ThreadPayload = FibreByType;

// ---------------------------------------------------------------------------
// Utility functions that mirror Pydantic model methods
// ---------------------------------------------------------------------------

/** Remove undefined / null keys recursively and sort keys for deterministic hashing. */
function sortedClean(obj: any): any {
  if (Array.isArray(obj)) return obj.map(sortedClean);
  if (obj !== null && typeof obj === "object") {
    const sorted: Record<string, any> = {};
    for (const k of Object.keys(obj).sort()) {
      const v = obj[k];
      if (v !== undefined && v !== null) {
        sorted[k] = sortedClean(v);
      }
    }
    return sorted;
  }
  return obj;
}

/** Compute a deterministic unique-key suffix (first 16 hex chars of SHA-256). */
export function uniqueKeySuffix(payload: Record<string, any>): string {
  const normalized = sortedClean(payload);
  const payloadStr = JSON.stringify(normalized);
  const hash = createHash("sha256").update(payloadStr, "utf-8").digest("hex");
  return hash.slice(0, 16);
}

/** Convert a fibre payload to a plain dict (stripping undefined). */
export function toDict(payload: Record<string, any>): Record<string, any> {
  return sortedClean(payload);
}

/** Get the `published` date as a Date, or null. */
export function getAsat(payload: { published?: string }): Date | null {
  if (!payload.published) return null;
  return new Date(payload.published);
}

// ---------------------------------------------------------------------------
// Preview helpers
// ---------------------------------------------------------------------------

export function getTextMessagePreview(msg: FibreTextMessage): string {
  const content = (msg.content as string) ?? "";
  const truncated =
    content.length > 100 ? content.slice(0, 100) + "..." : content;
  return `message "${truncated}"`;
}

export function getCreateObjectPreview(
  payload: FibreCreateObject,
  provider?: string,
): string {
  const objType = (payload.object["@type"] ?? "object").toLowerCase();
  let s = `Posted ${objType}`;
  if (provider) s += ` on ${provider}`;
  return s;
}

export function getSendMessagePreview(
  payload: FibreSendMessage,
  provider?: string,
): string {
  const objPreview = getObjectPreview(payload.object);
  const targetName = payload.target?.name ?? "unknown";
  let s = `Sent ${objPreview} to ${targetName}`;
  if (provider) s += ` on ${provider}`;
  return s;
}

export function getReceiveMessagePreview(
  payload: FibreReceiveMessage,
  provider?: string,
): string {
  const objPreview = getObjectPreview(payload.object);
  const actorName = payload.actor?.name ?? "unknown";
  let s = `Received ${objPreview} from ${actorName}`;
  if (provider) s += ` on ${provider}`;
  return s;
}

function getObjectPreview(
  obj: FibreTextMessage | FibreImage | FibreVideo,
): string {
  if (obj.fibre_kind === "TextMessage") return getTextMessagePreview(obj);
  if (obj.fibre_kind === "Image") return "image";
  if (obj.fibre_kind === "Video") return "video";
  return "object";
}

/** Get preview for any Fibre payload. */
export function getPreview(
  payload: FibreByType,
  provider?: string,
): string {
  switch (payload.fibre_kind) {
    case "TextMessage":
      return getTextMessagePreview(payload);
    case "Image":
      return "image";
    case "Video":
      return "video";
    case "Collection": {
      const parts = ["collection"];
      if (payload.name) parts.push(`"${payload.name}"`);
      return parts.join(" ");
    }
    case "Create":
      return getCreateObjectPreview(payload, provider);
    case "SendMessage":
      return getSendMessagePreview(payload, provider);
    case "ReceiveMessage":
      return getReceiveMessagePreview(payload, provider);
    default:
      return "unknown";
  }
}

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeApplication(name: string): ApplicationType {
  return { "@type": "Application", name };
}

export function makeProfile(
  name?: string,
  url?: string,
): ProfileType {
  const p: ProfileType = { "@type": "Profile" };
  if (name !== undefined) p.name = name;
  if (url !== undefined) p.url = url;
  return p;
}

export function makePerson(
  name?: string,
  url?: string,
): PersonType {
  const p: PersonType = { "@type": "Person" };
  if (name !== undefined) p.name = name;
  if (url !== undefined) p.url = url;
  return p;
}

export function makeCollection(opts?: {
  name?: string;
  id?: string;
}): CollectionType {
  const c: CollectionType = { "@type": "Collection" };
  if (opts?.name !== undefined) c.name = opts.name;
  if (opts?.id !== undefined) c["@id"] = opts.id;
  return c;
}

export function makeImage(opts: {
  url?: string;
  name?: string;
  published?: string;
}): ImageType {
  const img: ImageType = { "@type": "Image" };
  if (opts.url) img.url = opts.url;
  if (opts.name) img.name = opts.name;
  if (opts.published) img.published = opts.published;
  return img;
}

export function makeVideo(opts: {
  url?: string;
  name?: string;
  published?: string;
}): VideoType {
  const vid: VideoType = { "@type": "Video" };
  if (opts.url) vid.url = opts.url;
  if (opts.name) vid.name = opts.name;
  if (opts.published) vid.published = opts.published;
  return vid;
}

export function makeTextMessage(
  content: string,
  context?: CollectionType,
): FibreTextMessage {
  const msg: FibreTextMessage = {
    "@type": "Note",
    fibre_kind: "TextMessage",
    content,
  };
  if (context) msg.context = context;
  return msg;
}

export function makeSendMessage(opts: {
  object: FibreTextMessage | FibreImage | FibreVideo;
  target: ProfileType | ApplicationType;
  published?: string;
}): FibreSendMessage {
  const m: FibreSendMessage = {
    "@type": "Create",
    fibre_kind: "SendMessage",
    object: opts.object,
    target: opts.target,
  };
  if (opts.published) m.published = opts.published;
  return m;
}

export function makeReceiveMessage(opts: {
  object: FibreTextMessage | FibreImage | FibreVideo;
  actor: ProfileType | ApplicationType;
  published?: string;
}): FibreReceiveMessage {
  const m: FibreReceiveMessage = {
    "@type": "Create",
    fibre_kind: "ReceiveMessage",
    object: opts.object,
    actor: opts.actor,
  };
  if (opts.published) m.published = opts.published;
  return m;
}

export function makeCreateObject(opts: {
  object: ImageType | VideoType;
  published?: string;
}): FibreCreateObject {
  const c: FibreCreateObject = {
    "@type": "Create",
    fibre_kind: "Create",
    object: opts.object,
  };
  if (opts.published) c.published = opts.published;
  return c;
}

// ---------------------------------------------------------------------------
// Discriminated factory from raw dict (like Python's FibreTypeAdapter)
// ---------------------------------------------------------------------------

export function makeThreadPayload(data: Record<string, any>): ThreadPayload {
  const kind = data.fibre_kind;
  // Just return the data cast to the appropriate type — runtime validation
  // could be added with Zod if needed, but for now we trust internal producers.
  return data as ThreadPayload;
}

