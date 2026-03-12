from __future__ import annotations

from context_use.providers.google.search.pipe import _BaseGoogleSearchPipe
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig


class GoogleDiscoverPipe(_BaseGoogleSearchPipe):
    """Google Discover activity.

    Reuses the search-family extraction and transform logic since
    Discover produces the same Fibre types (``FibreViewObject``)
    with the ``Visited`` prefix.  Feed summary records
    (``"X cards in your feed"``) are filtered by the prefix check.
    """

    interaction_type = "google_discover"
    archive_path_pattern = "Portability/My Activity/Discover/MyActivity.json"


declare_interaction(InteractionConfig(pipe=GoogleDiscoverPipe, memory=None))
