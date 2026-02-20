from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import StrEnum

from context_use.etl.core.pipe import Pipe
from context_use.etl.models.etl_task import EtlTask
from context_use.etl.providers.chatgpt.conversations import (
    ChatGPTConversationsPipe,
)
from context_use.etl.providers.instagram.media import (
    InstagramReelsPipe,
    InstagramStoriesPipe,
)


class Provider(StrEnum):
    CHATGPT = "chatgpt"
    INSTAGRAM = "instagram"


@dataclass
class ProviderConfig:
    """Configuration for a single provider.

    Each provider registers one or more :class:`Pipe` subclasses.
    Task discovery and pipe lookup are derived from the registered
    pipes' class-level metadata (``archive_path_pattern``,
    ``interaction_type``).
    """

    pipes: list[type[Pipe]]

    def discover_tasks(
        self,
        archive_id: str,
        files: list[str],
        provider: str,
    ) -> list[EtlTask]:
        """Match extracted archive files against registered pipes.

        Uses :func:`fnmatch.fnmatch` to match each file against the
        pipe's ``archive_path_pattern``.  Patterns without wildcards
        behave as exact matches.  Patterns with wildcards create **one
        EtlTask per matched file** (fan-out).
        """
        prefix = f"{archive_id}/"
        tasks: list[EtlTask] = []
        for pipe_cls in self.pipes:
            pattern = f"{prefix}{pipe_cls.archive_path_pattern}"
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    tasks.append(
                        EtlTask(
                            archive_id=archive_id,
                            provider=provider,
                            interaction_type=pipe_cls.interaction_type,
                            source_uri=f,
                        )
                    )
        return tasks

    def get_pipe(self, interaction_type: str) -> type[Pipe]:
        """Look up the pipe class for *interaction_type*.

        Raises :class:`KeyError` if no pipe is registered for the
        given interaction type.
        """
        for pipe_cls in self.pipes:
            if pipe_cls.interaction_type == interaction_type:
                return pipe_cls
        raise KeyError(f"No pipe registered for interaction_type={interaction_type!r}")


PROVIDER_REGISTRY: dict[Provider, ProviderConfig] = {
    Provider.CHATGPT: ProviderConfig(
        pipes=[ChatGPTConversationsPipe],
    ),
    Provider.INSTAGRAM: ProviderConfig(
        pipes=[InstagramStoriesPipe, InstagramReelsPipe],
    ),
}


def get_provider_config(provider: Provider) -> ProviderConfig:
    """Look up the provider config. Raises ``KeyError`` for unknown providers."""
    return PROVIDER_REGISTRY[provider]
