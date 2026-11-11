"""Root-level pytest configuration.

Responsibilities:
1. Ensure the ``--basetemp`` parent directory exists before pytest's
   ``tmp_path_factory`` tries to create it (avoids FileNotFoundError on
   clean CI checkouts with no ``tmp/`` directory present).
2. Auto-apply directory-based markers so tests in ``tests/e2e/`` and
   ``tests/smoke/`` are always tagged correctly even if a test author
   forgets the ``pytestmark`` declaration.
3. ``GFLOW_TEST_SHARD=k/N``: keep only shard k's files (CI runs the 3.13 suite
   as parallel shards; see ``scripts/ci/shard_tests.py``).

The ``addopts`` and ``markers`` settings live in ``pyproject.toml`` so that
``pytest --help`` surfaces them correctly. See docs/E2E_TESTING.md for the
full marker reference and cost-tier run commands.
"""

from __future__ import annotations

import os
import pathlib

import pytest


def pytest_configure(config) -> None:  # noqa: ANN001 — pytest config object
    basetemp = config.getoption("basetemp", default=None)
    if basetemp:
        parent = pathlib.Path(basetemp).expanduser().resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
    spec = os.environ.get("GFLOW_TEST_SHARD")
    if spec:
        from scripts.ci.shard_tests import parse_spec

        config.pluginmanager.register(_Shard(*parse_spec(spec)), "gflow-test-shard")


class _Shard:
    """Deselect every file another shard owns.

    ``trylast`` so it splits only what ``-m`` left selected: the weights then cover
    the tests this run actually executes. Deselected, not skipped, so a shard's
    junit counts only its own tests and the summed count guard stays exact.
    """

    def __init__(self, index: int, total: int) -> None:
        self.index, self.total = index, total

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: list[pytest.Item]
    ) -> None:
        from scripts.ci.shard_tests import load_durations, shard_owner

        files = [item.nodeid.split("::")[0] for item in items]
        owner = shard_owner(files, self.total, load_durations())
        kept = [i for i, f in zip(items, files, strict=True) if owner[f] == self.index]
        dropped = [i for i, f in zip(items, files, strict=True) if owner[f] != self.index]
        if dropped:
            config.hook.pytest_deselected(items=dropped)
        items[:] = kept


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply markers based on the test file's directory.

    Tests under ``tests/e2e/`` receive ``pytest.mark.e2e`` if they don't
    already carry it. Tests under ``tests/smoke/`` receive ``pytest.mark.smoke``.
    This is a safety net — explicit ``pytestmark`` declarations in each file
    are still preferred and will be the canonical record.
    """
    for item in items:
        parts = item.path.parts
        # Adjacent-pair check: matches `.../tests/e2e/...` or `.../tests/smoke/...`
        # at any nesting depth. Prevents the false-positive a substring check
        # would have on a hypothetical `tests/api/e2e_helpers/test_x.py`.
        adjacent = set(zip(parts, parts[1:]))
        marker_names = {m.name for m in item.iter_markers()}
        if ("tests", "e2e") in adjacent and "e2e" not in marker_names:
            item.add_marker(pytest.mark.e2e)
        if ("tests", "smoke") in adjacent and "smoke" not in marker_names:
            item.add_marker(pytest.mark.smoke)
