from __future__ import annotations

from context_use.batch.grouper import CollectionGrouper, WindowGrouper
from context_use.memories.prompt.conversation import ConversationMemoryPromptBuilder
from context_use.memories.prompt.media import MediaMemoryPromptBuilder
from context_use.memories.registry import MemoryConfig, register_memory_config

# TODO(mez): move togher with etl registry
register_memory_config(
    "chatgpt_conversations",
    MemoryConfig(
        prompt_builder=ConversationMemoryPromptBuilder,
        grouper=CollectionGrouper,
    ),
)

_MEDIA_CONFIG = MemoryConfig(
    prompt_builder=MediaMemoryPromptBuilder,
    grouper=WindowGrouper,
)

for _itype in ("instagram_stories", "instagram_reels", "instagram_posts"):
    register_memory_config(_itype, _MEDIA_CONFIG)
