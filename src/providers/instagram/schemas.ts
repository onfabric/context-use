/**
 * Zod schemas for the real Instagram archive format.
 */
import { z } from "zod";

export const InstagramMediaItemSchema = z.object({
  uri: z.string(),
  creation_timestamp: z.number(),
  title: z.string().default(""),
  media_metadata: z.record(z.any()).optional().nullable(),
});

export const InstagramStoriesManifestSchema = z.object({
  ig_stories: z.array(InstagramMediaItemSchema),
});

export const InstagramReelsEntrySchema = z.object({
  media: z.array(InstagramMediaItemSchema),
});

export const InstagramReelsManifestSchema = z.object({
  ig_reels_media: z.array(InstagramReelsEntrySchema),
});

export type InstagramMediaItem = z.infer<typeof InstagramMediaItemSchema>;
export type InstagramStoriesManifest = z.infer<typeof InstagramStoriesManifestSchema>;
export type InstagramReelsEntry = z.infer<typeof InstagramReelsEntrySchema>;
export type InstagramReelsManifest = z.infer<typeof InstagramReelsManifestSchema>;

