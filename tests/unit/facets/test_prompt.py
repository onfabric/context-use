from __future__ import annotations

from context_use.facets.prompt import build_facet_description_prompt
from context_use.models.facet import Facet


def _make_facet(
    facet_type: str = "person",
    facet_canonical: str = "Alice",
) -> Facet:
    return Facet(facet_type=facet_type, facet_canonical=facet_canonical)


def test_prompt_item_id_is_facet_id() -> None:
    facet = _make_facet()
    item = build_facet_description_prompt(facet, ["Memory 1", "Memory 2"])
    assert item.item_id == facet.id


def test_prompt_includes_facet_type_and_canonical() -> None:
    facet = _make_facet(facet_type="location", facet_canonical="Tokyo")
    item = build_facet_description_prompt(facet, [])
    assert "location" in item.prompt
    assert "Tokyo" in item.prompt


def test_prompt_includes_all_memory_strings() -> None:
    memories = ["Visited the Eiffel Tower", "Had croissants for breakfast"]
    facet = _make_facet(facet_type="location", facet_canonical="Paris")
    item = build_facet_description_prompt(facet, memories)
    for memory in memories:
        assert memory in item.prompt


def test_prompt_has_response_schema() -> None:
    facet = _make_facet()
    item = build_facet_description_prompt(facet, ["Some memory"])
    assert item.response_schema is not None
    assert "short_description" in str(item.response_schema)
    assert "long_description" in str(item.response_schema)
