/**
 * ChatGPT conversations extraction + transform strategies.
 */
import { Readable } from "node:stream";
import { parser } from "stream-json";
import { streamArray } from "stream-json/streamers/StreamArray";

import type { ExtractionStrategy, TransformStrategy } from "../../core/etl.js";
import type { TaskMetadata, ThreadRow } from "../../core/types.js";
import type { StorageBackend } from "../../storage/backend.js";
import { ChatGPTMessageSchema } from "./schemas.js";
import {
  CURRENT_THREAD_PAYLOAD_VERSION,
  makeApplication,
  makeCollection,
  makeTextMessage,
  makeSendMessage,
  makeReceiveMessage,
  uniqueKeySuffix,
  toDict,
  getSendMessagePreview,
  getReceiveMessagePreview,
  type FibreSendMessage,
  type FibreReceiveMessage,
  type CollectionType,
} from "../../payload/models.js";

const CHATGPT_APPLICATION = makeApplication("assistant");
const CHUNK_SIZE = 500;

/** Timestamps above this threshold are treated as milliseconds (year 2100+). */
const MAX_SECONDS_EPOCH = 4_102_444_800;

function safeTimestamp(ts: number | null | undefined): Date | null {
  if (ts == null) return null;
  let val = Number(ts);
  if (val > MAX_SECONDS_EPOCH) val /= 1000;
  return new Date(val * 1000);
}

// ---------------------------------------------------------------------------
// Extraction
// ---------------------------------------------------------------------------

export class ChatGPTConversationsExtractionStrategy
  implements ExtractionStrategy
{
  async extract(
    task: TaskMetadata,
    storage: StorageBackend,
  ): Promise<Record<string, any>[][]> {
    const key = task.filenames[0];
    const data = await storage.read(key);

    return new Promise<Record<string, any>[][]>((resolve, reject) => {
      const batches: Record<string, any>[][] = [];
      let chunk: Record<string, any>[] = [];
      let rejected = false;
      const onError = (err: Error) => {
        if (!rejected) {
          rejected = true;
          reject(err);
        }
      };

      const nodeStream = Readable.from(Buffer.from(data));
      const jsonParser = parser();
      const arrayStream = streamArray();

      nodeStream.on("error", onError);
      jsonParser.on("error", onError);
      arrayStream.on("error", onError);

      const pipeline = nodeStream.pipe(jsonParser).pipe(arrayStream);

      pipeline.on("data", ({ value: conversation }: { value: any }) => {
        const conversationTitle = conversation.title ?? null;
        const conversationId = conversation.conversation_id ?? null;
        const mapping: Record<string, any> = conversation.mapping ?? {};

        for (const mappingItem of Object.values(mapping)) {
          const messageData = (mappingItem as any).message;
          if (!messageData) continue;
          if (!messageData.author || !messageData.content) continue;

          const content = messageData.content ?? {};
          if (content.content_type !== "text") continue;

          const parsed = ChatGPTMessageSchema.safeParse(messageData);
          if (!parsed.success) continue;
          const msg = parsed.data;

          if (msg.author.role === "system") continue;
          if (!msg.content.parts || !msg.content.parts[0]) continue;
          const text = msg.content.parts[0];
          if (!text.trim()) continue;

          const createTime = msg.create_time ?? null;

          chunk.push({
            role: msg.author.role,
            content: text,
            create_time: createTime,
            conversation_id: conversationId,
            conversation_title: conversationTitle,
            source: JSON.stringify(messageData),
          });

          if (chunk.length >= CHUNK_SIZE) {
            batches.push(chunk);
            chunk = [];
          }
        }
      });

      pipeline.on("end", () => {
        if (chunk.length > 0) batches.push(chunk);
        resolve(batches);
      });

      pipeline.on("error", onError);
    });
  }
}

// ---------------------------------------------------------------------------
// Transform
// ---------------------------------------------------------------------------

export class ChatGPTConversationsTransformStrategy
  implements TransformStrategy
{
  async transform(
    task: TaskMetadata,
    batches: Record<string, any>[][],
  ): Promise<ThreadRow[][]> {
    const resultBatches: ThreadRow[][] = [];

    for (const batch of batches) {
      const rows: ThreadRow[] = [];
      for (const record of batch) {
        const payload = this.buildPayload(record);
        if (!payload) continue;

        const createTime = record.create_time;
        const asat = safeTimestamp(createTime) ?? new Date();

        const dict = toDict(payload);
        rows.push({
          uniqueKey: `chatgpt_conversations:${uniqueKeySuffix(dict)}`,
          provider: task.provider,
          interactionType: task.interactionType,
          preview:
            payload.fibre_kind === "SendMessage"
              ? getSendMessagePreview(payload as FibreSendMessage, "ChatGPT")
              : getReceiveMessagePreview(
                  payload as FibreReceiveMessage,
                  "ChatGPT",
                ),
          payload: dict,
          source: record.source ?? null,
          version: CURRENT_THREAD_PAYLOAD_VERSION,
          asat,
          assetUri: null,
        });
      }
      if (rows.length > 0) resultBatches.push(rows);
    }

    return resultBatches;
  }

  private buildPayload(
    record: Record<string, any>,
  ): FibreSendMessage | FibreReceiveMessage | null {
    const role: string = record.role;
    const content: string = record.content;
    const conversationTitle: string | null = record.conversation_title ?? null;
    const conversationId: string | null = record.conversation_id ?? null;

    let context: CollectionType | undefined;
    if (conversationTitle || conversationId) {
      context = makeCollection({
        name: conversationTitle ?? undefined,
        id: conversationId
          ? `https://chatgpt.com/c/${conversationId}`
          : undefined,
      });
    }

    const message = makeTextMessage(content, context);

    const createTime = record.create_time;
    const published = safeTimestamp(createTime);
    const publishedStr = published?.toISOString();

    if (role === "user") {
      return makeSendMessage({
        object: message,
        target: CHATGPT_APPLICATION,
        published: publishedStr,
      });
    } else if (role === "assistant") {
      return makeReceiveMessage({
        object: message,
        actor: CHATGPT_APPLICATION,
        published: publishedStr,
      });
    }

    return null;
  }
}

