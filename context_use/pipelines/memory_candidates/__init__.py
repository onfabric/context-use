"""Memory-candidates pipeline.

Import this module to register the batch state parser and manager
for ``BatchCategory.memory_candidates``.
"""

# Side-effect imports: register state parser and batch manager
from context_use.pipelines.memory_candidates.factory import (  # noqa: F401
    MemoryCandidateBatchFactory,
)
from context_use.pipelines.memory_candidates.manager import (  # noqa: F401
    MemoryCandidateBatchManager,
)
from context_use.pipelines.memory_candidates.states import (  # noqa: F401
    parse_memory_candidate_batch_state,
)
