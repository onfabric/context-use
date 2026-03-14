from __future__ import annotations

from context_use.providers.google.search.pipe import _BaseGoogleSearchPipe
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig


class GoogleDiscoverPipe(_BaseGoogleSearchPipe):
    interaction_type = "google_discover"
    archive_path_pattern = "Portability/My Activity/Discover/MyActivity.json"


declare_interaction(InteractionConfig(pipe=GoogleDiscoverPipe, memory=None))
