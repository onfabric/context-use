from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from context_use.etl.core.pipe import Pipe
from context_use.memories.config import MemoryConfig
from context_use.models.etl_task import EtlTask


@dataclass
class InteractionConfig:
    """Full pipeline config for one interaction type: ETL pipe + memory generation.

    ``pipes`` holds one or more :class:`Pipe` subclasses for the same
    ``interaction_type``, ordered newest-first by ``archive_version``
    (auto-sorted in ``__post_init__``).  During discovery the newest
    matching version wins; during execution the facade can fall back to
    older versions on schema errors.
    """

    pipes: list[type[Pipe]] = field(default_factory=list)
    memory: MemoryConfig | None = None

    def __post_init__(self) -> None:
        if not self.pipes:
            raise ValueError("pipes must not be empty")
        # Auto-sort newest-first (highest archive_version first).
        self.pipes = sorted(self.pipes, key=lambda p: p.archive_version, reverse=True)
        # All pipes must share the same interaction_type.
        types = {p.interaction_type for p in self.pipes}
        if len(types) != 1:
            raise ValueError(
                f"All pipes must share the same interaction_type, got {types}"
            )

    @property
    def pipe(self) -> type[Pipe]:
        """Backward-compat accessor returning the newest pipe."""
        return self.pipes[0]

    @property
    def interaction_type(self) -> str:
        """The interaction type shared by all pipes in this config."""
        return self.pipes[0].interaction_type


@dataclass
class ProviderConfig:
    """Configuration for a single provider.

    Each provider registers one or more :class:`InteractionConfig` entries.
    Task discovery and pipe lookup are derived from the registered
    pipes' class-level metadata (``archive_path_pattern``,
    ``interaction_type``).
    """

    interactions: list[InteractionConfig]

    def discover_tasks(
        self,
        archive_id: str,
        files: list[str],
        provider: str,
    ) -> list[EtlTask]:
        """Match extracted archive files against registered pipes.

        For each :class:`InteractionConfig`, tries each pipe's
        ``archive_path_pattern`` newest-first.  On the first file
        match, creates **one EtlTask** and moves to the next
        interaction type.  All matched files for the winning pattern
        are bundled into ``source_uris`` (sorted for determinism).
        """
        prefix = f"{archive_id}/"
        tasks: list[EtlTask] = []
        for ic in self.interactions:
            for pipe_cls in ic.pipes:  # already sorted newest-first
                pattern = f"{prefix}{pipe_cls.archive_path_pattern}"
                matched = sorted(f for f in files if fnmatch.fnmatch(f, pattern))
                if matched:
                    tasks.append(
                        EtlTask(
                            archive_id=archive_id,
                            provider=provider,
                            interaction_type=ic.interaction_type,
                            source_uris=matched,
                        )
                    )
                    break
        return tasks

    def get_pipe_chain(self, interaction_type: str) -> list[type[Pipe]]:
        """Return the full ordered pipe list for *interaction_type*.

        The list is sorted newest-first (highest ``archive_version``
        first).  This is the primary primitive for fallback loops.

        Raises :class:`KeyError` if no interaction is registered for
        the given interaction type.
        """
        for ic in self.interactions:
            if ic.interaction_type == interaction_type:
                return ic.pipes
        raise KeyError(f"No pipe chain for interaction_type={interaction_type!r}")

    def get_pipe(self, interaction_type: str) -> type[Pipe]:
        """Look up the newest pipe class for *interaction_type*.

        Convenience wrapper around :meth:`get_pipe_chain` returning
        the first (newest) entry.

        Raises :class:`KeyError` if no pipe is registered for the
        given interaction type.
        """
        return self.get_pipe_chain(interaction_type)[0]

    def get_memory_config(self, interaction_type: str) -> MemoryConfig:
        """Look up the memory config for *interaction_type*.

        Raises :class:`KeyError` if no interaction or memory config is
        registered for the given interaction type.
        """
        for ic in self.interactions:
            if ic.interaction_type == interaction_type:
                if ic.memory is None:
                    raise KeyError(
                        f"No memory config for interaction_type={interaction_type!r}"
                    )
                return ic.memory
        raise KeyError(
            f"No interaction config for interaction_type={interaction_type!r}"
        )
