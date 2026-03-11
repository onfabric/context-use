from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import tests.unit.etl as _etl_tests_pkg
from context_use.etl.core.pipe import Pipe
from context_use.providers import get_provider_config, list_providers
from context_use.testing import PipeTestKit

_KitMap = dict[type[Pipe], type[PipeTestKit]]


def _discover_test_kit_classes() -> _KitMap:
    kits: _KitMap = {}
    pkg_prefix = f"{_etl_tests_pkg.__name__}."
    for info in pkgutil.walk_packages(_etl_tests_pkg.__path__, prefix=pkg_prefix):
        mod = importlib.import_module(info.name)
        for _name, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, PipeTestKit) and obj is not PipeTestKit:
                pipe_cls = getattr(obj, "pipe_class", None)
                if pipe_cls is not None:
                    kits[pipe_cls] = obj
    return kits


def _all_registered_pipes() -> list[type[Pipe]]:
    pipes: list[type[Pipe]] = []
    for provider in list_providers():
        cfg = get_provider_config(provider)
        pipes.extend(cfg.pipes)
    return pipes


@pytest.fixture(scope="module")
def pipe_kit_map() -> _KitMap:
    return _discover_test_kit_classes()


class TestPipeCoverage:
    def test_every_registered_pipe_has_test_kit(self, pipe_kit_map: _KitMap) -> None:
        missing: list[str] = []
        for pipe_cls in _all_registered_pipes():
            if pipe_cls not in pipe_kit_map:
                missing.append(f"{pipe_cls.__module__}.{pipe_cls.__name__}")
        assert not missing, (
            "The following registered pipes have no "
            "PipeTestKit test class:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\n\nAdd a PipeTestKit subclass in "
            "tests/unit/etl/<provider>/."
        )
