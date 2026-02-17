/**
 * Instagram orchestration strategy.
 */
import { OrchestrationStrategy } from "../../core/etl.js";

export class InstagramOrchestrationStrategy extends OrchestrationStrategy {
  readonly MANIFEST_MAP: Record<string, string> = {
    "your_instagram_activity/media/stories.json": "instagram_stories",
    "your_instagram_activity/media/reels.json": "instagram_reels",
  };
}

