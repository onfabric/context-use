from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from context_use.etl.core.pipe import Pipe
from context_use.etl.models.etl_task import EtlTask
from context_use.memories.config import MemoryConfig


@dataclass
class InteractionConfig:
    """Full pipeline config for one interaction type: ETL pipe + memory generation."""

    pipe: type[Pipe]
    memory: MemoryConfig | None = None


@dataclass
class ProviderConfig:
    """Configuration for a single provider.

    Each provider registers one or more :class:`InteractionConfig` entries.
    Task discovery and pipe lookup are derived from the registered
    pipes' class-level metadata (``archive_path_pattern``,
    ``interaction_type``).
    """

    interactions: list[InteractionConfig]

    @property
    def pipes(self) -> list[type[Pipe]]:
        return [i.pipe for i in self.interactions]

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

    def get_memory_config(self, interaction_type: str) -> MemoryConfig:
        """Look up the memory config for *interaction_type*.

        Raises :class:`KeyError` if no interaction or memory config is
        registered for the given interaction type.
        """
        for ic in self.interactions:
            if ic.pipe.interaction_type == interaction_type:
                if ic.memory is None:
                    raise KeyError(
                        f"No memory config for interaction_type={interaction_type!r}"
                    )
                return ic.memory
        raise KeyError(
            f"No interaction config for interaction_type={interaction_type!r}"
        )
