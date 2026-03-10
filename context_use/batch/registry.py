
from collections.abc import Callable
from typing import TYPE_CHECKING

from context_use.models.batch import BatchCategory

if TYPE_CHECKING:
    from context_use.batch.states import State

_batch_state_parsers: dict[BatchCategory, Callable[[dict], State]] = {}


def register_batch_state_parser(category: BatchCategory):
    """Decorator: register a state-dict → State parser for *category*."""

    def decorator(fn: Callable[[dict], State]) -> Callable[[dict], State]:
        _batch_state_parsers[category] = fn
        return fn

    return decorator


def parse_batch_state(state_dict: dict, category: BatchCategory) -> State:
    """Dispatch to the correct parser for *category*."""
    parser = _batch_state_parsers.get(category)
    if parser is None:
        raise ValueError(
            f"No state parser registered for batch category: {category.value}"
        )
    return parser(state_dict)
