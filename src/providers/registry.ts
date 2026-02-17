/**
 * Provider registry – maps Provider enum values to orchestration / strategy classes.
 */
import type { OrchestrationStrategy, ExtractionStrategy, TransformStrategy } from "../core/etl.js";
import { ChatGPTOrchestrationStrategy } from "./chatgpt/orchestration.js";
import {
  ChatGPTConversationsExtractionStrategy,
  ChatGPTConversationsTransformStrategy,
} from "./chatgpt/conversations.js";
import { InstagramOrchestrationStrategy } from "./instagram/orchestration.js";
import {
  InstagramStoriesExtractionStrategy,
  InstagramStoriesTransformStrategy,
  InstagramReelsExtractionStrategy,
  InstagramReelsTransformStrategy,
} from "./instagram/media.js";

// ---------------------------------------------------------------------------
// Provider enum
// ---------------------------------------------------------------------------

export enum Provider {
  ChatGPT = "chatgpt",
  Instagram = "instagram",
}

// ---------------------------------------------------------------------------
// Config types
// ---------------------------------------------------------------------------

export interface InteractionTypeConfig {
  extraction: new () => ExtractionStrategy;
  transform: new () => TransformStrategy;
}

export interface ProviderConfig {
  orchestration: new () => OrchestrationStrategy;
  interactionTypes: Record<string, InteractionTypeConfig>;
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

export const PROVIDER_REGISTRY: Record<string, ProviderConfig> = {
  [Provider.ChatGPT]: {
    orchestration: ChatGPTOrchestrationStrategy,
    interactionTypes: {
      chatgpt_conversations: {
        extraction: ChatGPTConversationsExtractionStrategy,
        transform: ChatGPTConversationsTransformStrategy,
      },
    },
  },
  [Provider.Instagram]: {
    orchestration: InstagramOrchestrationStrategy,
    interactionTypes: {
      instagram_stories: {
        extraction: InstagramStoriesExtractionStrategy,
        transform: InstagramStoriesTransformStrategy,
      },
      instagram_reels: {
        extraction: InstagramReelsExtractionStrategy,
        transform: InstagramReelsTransformStrategy,
      },
    },
  },
};

export function getProviderConfig(provider: string): ProviderConfig {
  const cfg = PROVIDER_REGISTRY[provider];
  if (!cfg) throw new Error(`Unknown provider: ${provider}`);
  return cfg;
}

