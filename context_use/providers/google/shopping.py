from context_use.providers.google.search import _BaseGoogleSearchPipe
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig


class GoogleShoppingPipe(_BaseGoogleSearchPipe):
    """Google Shopping activity.

    Reuses the search-family extraction and transform logic since
    Shopping produces the same Fibre types (``FibreSearch``,
    ``FibreViewObject``) with the same title prefixes.
    """

    interaction_type = "google_shopping"
    archive_path_pattern = "Portability/My Activity/Shopping/MyActivity.json"


declare_interaction(InteractionConfig(pipe=GoogleShoppingPipe, memory=None))
