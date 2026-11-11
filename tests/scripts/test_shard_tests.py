"""Unit tests for the CI shard split (`scripts/ci/shard_tests.py`).

CI runs the 3.13 suite as parallel shards (`GFLOW_TEST_SHARD=k/N`). The split is
by whole file, so module fixtures never straddle two processes. It is balanced on
recorded per-file durations, so the shards finish together. A file that is
dropped or counted twice is a test that silently never runs, or runs twice, so
those properties are what is pinned here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import shard_tests

_FILES = [f"tests/test_{c}.py" for c in "abcdefghij"]
_DURATIONS = {f: float(i + 1) for i, f in enumerate(_FILES)}


@pytest.mark.parametrize("total", [1, 2, 3, 4])
def test_every_file_lands_in_exactly_one_shard(total: int) -> None:
    owner = shard_tests.shard_owner(_FILES, total, _DURATIONS)
    assert set(owner) == set(_FILES)
    assert set(owner.values()) <= set(range(total))


def test_the_split_is_deterministic_whatever_the_input_order() -> None:
    once = shard_tests.shard_owner(_FILES, 3, _DURATIONS)
    again = shard_tests.shard_owner(list(reversed(_FILES)), 3, _DURATIONS)
    assert once == again


def test_shards_are_balanced_on_recorded_time() -> None:
    owner = shard_tests.shard_owner(_FILES, 2, _DURATIONS)
    loads = [sum(_DURATIONS[f] for f in _FILES if owner[f] == k) for k in range(2)]
    assert abs(loads[0] - loads[1]) <= max(_DURATIONS.values())


def test_an_unknown_file_counts_as_the_average() -> None:
    durations = {"tests/test_big.py": 10.0, "tests/test_small.py": 2.0}
    weights = shard_tests.file_weights([*durations, "tests/test_new.py"], durations)
    assert weights["tests/test_new.py"] == pytest.approx(6.0)


def test_no_recorded_durations_still_splits_every_file() -> None:
    owner = shard_tests.shard_owner(_FILES, 3, {})
    assert set(owner) == set(_FILES)
    assert sorted(owner.values()).count(0) >= 3


@pytest.mark.parametrize("spec", ["", "3", "0/2", "3/2", "a/b", "1/0"])
def test_a_malformed_shard_spec_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="GFLOW_TEST_SHARD"):
        shard_tests.parse_spec(spec)


def test_parse_spec_returns_a_zero_based_index() -> None:
    assert shard_tests.parse_spec("2/3") == (1, 3)


def test_durations_are_recorded_per_file_from_junit(tmp_path: Path) -> None:
    """Classnames carry the module path plus any test class; both map to the file."""
    (tmp_path / "tests" / "pkg").mkdir(parents=True)
    (tmp_path / "tests" / "pkg" / "test_x.py").write_text("", encoding="utf-8")
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="tests.pkg.test_x" name="a" time="1.5"/>'
        '<testcase classname="tests.pkg.test_x.TestThing" name="b" time="2.0"/>'
        '<testcase classname="tests.gone.test_y" name="c" time="9.0"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    assert shard_tests.durations_from_junit([junit], root=tmp_path) == {"tests/pkg/test_x.py": 3.5}


def test_the_committed_durations_file_is_valid_json_of_seconds() -> None:
    data = json.loads(shard_tests.DURATIONS_FILE.read_text(encoding="utf-8"))
    assert data, "tests/test_durations.json is empty"
    assert all(k.startswith("tests/") and k.endswith(".py") for k in data)
    assert all(isinstance(v, (int, float)) and v >= 0 for v in data.values())
