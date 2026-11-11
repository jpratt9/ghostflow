"""Tests for the advisory deletion check (#713).

Each test builds a throwaway git repo: a ``base`` branch, then a change on a
feature branch, and runs the check against ``base`` from inside that repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import check_deletions as cd


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "base")
    _git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "STATUS.md").write_text(
        "".join(f"line {i}\n" for i in range(200)), encoding="utf-8"
    )
    (tmp_path / "scripts" / "autopilot").mkdir(parents=True)
    (tmp_path / "scripts" / "autopilot" / "run.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "scripts" / "keep.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# readme\n", encoding="utf-8")
    _commit(tmp_path, "base")
    _git(tmp_path, "switch", "-q", "-c", "feature")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return tmp_path


def test_gutted_doc_warns(repo: Path) -> None:
    (repo / "docs" / "STATUS.md").write_text("only\n", encoding="utf-8")
    _commit(repo, "gut")
    findings = cd.gutted_docs("base")
    assert len(findings) == 1
    assert "docs/STATUS.md" in findings[0]


def test_small_doc_edit_does_not_warn(repo: Path) -> None:
    lines = [f"line {i}\n" for i in range(200)]
    del lines[10:20]
    (repo / "docs" / "STATUS.md").write_text("".join(lines), encoding="utf-8")
    _commit(repo, "trim")
    assert cd.gutted_docs("base") == []


def test_deleted_dir_still_referenced_from_yaml_is_reported(repo: Path) -> None:
    (repo / ".github").mkdir()
    (repo / ".github" / "labeler.yml").write_text(
        'rules:\n  - directory: "/scripts/autopilot"\n', encoding="utf-8"
    )
    _commit(repo, "labeler")
    _git(repo, "switch", "-q", "-c", "feature2")
    _git(repo, "rm", "-q", "-r", "scripts/autopilot")
    _commit(repo, "drop autopilot")
    findings = cd.orphaned_references("feature")
    assert any(".github/labeler.yml:2" in f and "scripts/autopilot" in f for f in findings)


def test_top_level_dir_matches_as_a_path_not_a_word(repo: Path) -> None:
    (repo / "eval").mkdir()
    (repo / "eval" / "x.py").write_text("z = 1\n", encoding="utf-8")
    (repo / "NOTES.md").write_text("we eval things\nsee eval/x.py\n", encoding="utf-8")
    _commit(repo, "eval")
    _git(repo, "switch", "-q", "-c", "feature2")
    _git(repo, "rm", "-q", "-r", "eval")
    _commit(repo, "drop eval")
    findings = cd.orphaned_references("feature")
    assert [f.split(": ")[0] for f in findings] == ["NOTES.md:2"]


def test_reference_only_in_changelog_is_ignored(repo: Path) -> None:
    (repo / "CHANGELOG.md").write_text("- removed scripts/autopilot\n", encoding="utf-8")
    _git(repo, "rm", "-q", "-r", "scripts/autopilot")
    _commit(repo, "drop autopilot")
    assert cd.orphaned_references("base") == []


def test_nothing_deleted_reports_nothing_and_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "scripts" / "keep.py").write_text("y = 3\n", encoding="utf-8")
    _commit(repo, "edit")
    assert cd.main(["--base", "base"]) == 0
    assert "::warning::" not in capsys.readouterr().out


def test_findings_still_exit_zero_and_write_summary(
    repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (repo / "docs" / "STATUS.md").write_text("only\n", encoding="utf-8")
    _commit(repo, "gut")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert cd.main(["--base", "base"]) == 0
    assert "docs/STATUS.md" in summary.read_text(encoding="utf-8")


def test_unknown_base_is_a_usage_error(repo: Path) -> None:
    assert cd.main(["--base", "no-such-ref"]) == 2
