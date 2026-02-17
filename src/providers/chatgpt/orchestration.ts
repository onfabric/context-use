/**
 * ChatGPT orchestration strategy.
 */
import { OrchestrationStrategy } from "../../core/etl.js";

export class ChatGPTOrchestrationStrategy extends OrchestrationStrategy {
  readonly MANIFEST_MAP: Record<string, string> = {
    "conversations.json": "chatgpt_conversations",
  };
}

