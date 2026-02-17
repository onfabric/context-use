/**
 * Zod schemas for raw ChatGPT archive data.
 */
import { z } from "zod";

export const ChatGPTAuthorSchema = z.object({
  role: z.string(),
});

export const ChatGPTContentSchema = z.object({
  content_type: z.string().optional().nullable(),
  parts: z.array(z.string()).optional().nullable(),
});

export const ChatGPTMessageSchema = z.object({
  author: ChatGPTAuthorSchema,
  content: ChatGPTContentSchema,
  create_time: z.number().optional().nullable(),
});

export type ChatGPTAuthor = z.infer<typeof ChatGPTAuthorSchema>;
export type ChatGPTContent = z.infer<typeof ChatGPTContentSchema>;
export type ChatGPTMessage = z.infer<typeof ChatGPTMessageSchema>;

