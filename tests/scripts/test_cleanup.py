"""scripts/dev/cleanup.py — post-session resource cleanup.

Worktree and branch logic runs against a REAL temporary git repository (a bare
``origin`` plus a clone); only ``gh`` and agentctl are faked, through the one
``run`` seam the script takes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

# scripts/ is outside pyright's include and is not a package — load by path.
_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "cleanup.py"
_spec = importlib.util.spec_from_file_location("cleanup", _MOD_PATH)
assert _spec is not None and _spec.loader is not None
cleanup: Any = importlib.util.module_from_spec(_spec)
sys.modules["cleanup"] = cleanup
_spec.loader.exec_module(cleanup)

_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
_MUTATING = (
    ("worktree", "remove"),
    ("worktree", "prune"),
    ("branch", "-D"),
    ("push",),
)


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run([*_GIT, "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _commit(cwd: Path, name: str) -> None:
    (cwd / name).write_text(name, encoding="utf-8")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", name)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "develop", str(origin)], check=True)
    clone = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    _commit(clone, "a")
    _git(clone, "push", "-q", "origin", "develop")
    _git(clone, "branch", "main")
    _git(clone, "push", "-q", "origin", "main")
    return clone


def _merged_worktree(repo: Path, branch: str) -> Path:
    """A worktree on ``branch`` whose commit is merged into origin/develop."""
    wt = repo.parent / f"wt-{branch.replace('/', '-')}"
    _git(repo, "worktree", "add", "-q", "-b", branch, str(wt))
    _commit(wt, f"{branch.replace('/', '-')}.txt")
    _git(repo, "merge", "-q", "--ff-only", branch)
    _git(repo, "push", "-q", "origin", "develop")
    return wt


def _unmerged_worktree(repo: Path, branch: str) -> Path:
    wt = repo.parent / f"wt-{branch.replace('/', '-')}"
    _git(repo, "worktree", "add", "-q", "-b", branch, str(wt))
    _commit(wt, f"{branch.replace('/', '-')}.txt")
    return wt


class Recorder:
    """Real subprocess for git; canned answers for gh and agentctl; logs every command."""

    def __init__(self, prs: list[dict[str, object]] | None = None, agentctl_out: str = "") -> None:
        self.prs = prs
        self.agentctl_out = agentctl_out
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(cmd))
        if cmd[0] == "gh":
            if self.prs is None:
                raise FileNotFoundError("gh")
            return subprocess.CompletedProcess(cmd, 0, json.dumps(self.prs), "")
        if any("agentctl" in part for part in cmd):
            return subprocess.CompletedProcess(cmd, 0, self.agentctl_out, "")
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)

    def mutations(self) -> list[list[str]]:
        found: list[list[str]] = []
        for cmd in self.calls:
            if cmd[0] != "git":
                continue
            rest = [p for p in cmd[1:] if p not in ("-C",)]
            for sig in _MUTATING:
                if any(rest[i : i + len(sig)] == list(sig) for i in range(len(rest))):
                    found.append(cmd)
        return found


def _plan(repo: Path, run: Recorder, tmp_root: Path | None = None, **kw: Any) -> Any:
    root = tmp_root if tmp_root is not None else repo.parent / "no-temp"
    root.mkdir(exist_ok=True)
    return cleanup.build_plan(
        repo,
        base=kw.pop("base", "origin/develop"),
        run=run,
        remote=kw.pop("remote", False),
        tmp_root=root,
        older_than_hours=kw.pop("older_than_hours", 1.0),
        agentctl=kw.pop("agentctl", None),
    )


def _paths(entries: list[tuple[Path, str]]) -> set[Path]:
    return {p.resolve() for p, _ in entries}


# --- worktrees -----------------------------------------------------------------------


def _done(branch: str, number: int = 1, state: str = "MERGED") -> dict[str, object]:
    return {"headRefName": branch, "state": state, "number": number, "isCrossRepository": False}


def test_worktree_whose_pr_is_merged_is_selected(repo: Path) -> None:
    wt = _merged_worktree(repo, "feature/done")
    plan = _plan(repo, Recorder(prs=[_done("feature/done")]))
    assert wt.resolve() in _paths(plan.worktrees)


def test_a_merged_worktree_with_no_pr_is_kept(repo: Path) -> None:
    """Ancestry alone cannot tell a finished branch from one an agent just started."""
    wt = _merged_worktree(repo, "feature/done")
    plan = _plan(repo, Recorder(prs=[]))
    assert wt.resolve() not in _paths(plan.worktrees)


def test_a_fresh_unstarted_worktree_is_kept(repo: Path) -> None:
    """Right after `switch -c x origin/develop` the tip is in the base — and in use."""
    wt = repo.parent / "wt-fresh"
    _git(repo, "worktree", "add", "-q", "-b", "feature/fresh", str(wt), "origin/develop")
    plan = _plan(repo, Recorder(prs=[]))
    assert wt.resolve() not in _paths(plan.worktrees)
    assert "feature/fresh" not in plan.branches


def test_a_locked_worktree_is_kept(repo: Path) -> None:
    wt = _merged_worktree(repo, "feature/held")
    _git(repo, "worktree", "lock", str(wt))
    plan = _plan(repo, Recorder(prs=[_done("feature/held")]))
    assert wt.resolve() not in _paths(plan.worktrees)
    assert any(p.resolve() == wt.resolve() and "locked" in why for p, why in plan.kept)


def test_never_selects_the_main_checkout(repo: Path) -> None:
    _merged_worktree(repo, "feature/done")
    plan = _plan(repo, Recorder(prs=[_done("feature/done")]))
    assert repo.resolve() not in _paths(plan.worktrees)


def test_never_selects_the_main_checkout_when_run_from_a_linked_worktree(repo: Path) -> None:
    """The `i == 0` guard: from a linked worktree, the main checkout is not `here`."""
    _git(repo, "switch", "-q", "-c", "feature/main-done")
    _git(repo, "switch", "-q", "--detach")
    linked = repo.parent / "wt-runner"
    _git(repo, "worktree", "add", "-q", "-b", "feature/runner", str(linked))
    _git(repo, "switch", "-q", "feature/main-done")
    plan = _plan(linked, Recorder(prs=[_done("feature/main-done")]))
    assert repo.resolve() not in _paths(plan.worktrees)


def test_unmerged_worktree_without_a_pr_is_not_selected(repo: Path) -> None:
    wt = _unmerged_worktree(repo, "feature/wip")
    plan = _plan(repo, Recorder(prs=[]))
    assert wt.resolve() not in _paths(plan.worktrees)
    assert "feature/wip" not in plan.branches


def test_dirty_merged_worktree_is_kept_as_dirty(repo: Path) -> None:
    wt = _merged_worktree(repo, "feature/dirty")
    (wt / "scratch.txt").write_text("x", encoding="utf-8")
    # a done PR makes it removable, so only the dirty guard keeps it
    plan = _plan(repo, Recorder(prs=[_done("feature/dirty")]))
    assert wt.resolve() not in _paths(plan.worktrees)
    assert any(p.resolve() == wt.resolve() and "dirty" in why for p, why in plan.kept)
    # its branch is checked out in a remaining worktree, so it stays too
    assert "feature/dirty" not in plan.branches


def test_worktree_whose_pr_is_merged_is_selected_even_if_not_ancestor(repo: Path) -> None:
    wt = _unmerged_worktree(repo, "feature/squashed")
    prs = [
        {
            "headRefName": "feature/squashed",
            "state": "MERGED",
            "number": 7,
            "isCrossRepository": False,
        }
    ]
    plan = _plan(repo, Recorder(prs=prs))
    assert wt.resolve() in _paths(plan.worktrees)


def test_missing_gh_is_skipped_silently(repo: Path) -> None:
    wt = _merged_worktree(repo, "feature/done")
    plan = _plan(repo, Recorder(prs=None))
    # without PR facts nothing proves the worktree is finished: kept, and no crash
    assert wt.resolve() not in _paths(plan.worktrees)
    assert "feature/done" not in plan.branches


def test_detached_worktree_contained_in_base_is_selected(repo: Path) -> None:
    wt = repo.parent / "wt-detached"
    _git(repo, "worktree", "add", "-q", "--detach", str(wt), "origin/develop")
    plan = _plan(repo, Recorder(prs=[]))
    assert wt.resolve() in _paths(plan.worktrees)


def test_dry_run_performs_zero_mutations(repo: Path, tmp_path: Path) -> None:
    wt = _merged_worktree(repo, "feature/done")
    (_unmerged_worktree(repo, "feature/kept") / ".env").write_text("K=1", encoding="utf-8")
    temps = tmp_path / "temps"
    old = temps / "btcl1"
    old.mkdir(parents=True)
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    run = Recorder(prs=[])
    rc = cleanup.main(["--repo", str(repo), "--no-fetch", "--remote"], run=run, tmp_root=temps)
    assert rc == 0
    assert run.mutations() == []
    assert wt.exists() and old.exists()
    assert (repo.parent / "wt-feature-kept" / ".env").exists()
    assert "feature/done" in _git(repo, "branch", "--list", "feature/done")


def test_apply_removes_worktree_and_merged_branch(repo: Path) -> None:
    wt = _merged_worktree(repo, "feature/done")
    run = Recorder(prs=[_done("feature/done")])
    plan = _plan(repo, run)
    problems = cleanup.apply_plan(plan, repo, run)
    assert problems == []
    assert not wt.exists()
    assert _git(repo, "branch", "--list", "feature/done") == ""


def test_locked_worktree_removal_is_reported_not_raised(repo: Path) -> None:
    _merged_worktree(repo, "feature/locked")

    class Locked(Recorder):
        def __call__(
            self, cmd: list[str], cwd: Path | None = None
        ) -> subprocess.CompletedProcess[str]:
            if "remove" in cmd and "worktree" in cmd:
                self.calls.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 1, "", "Permission denied")
            return super().__call__(cmd, cwd)

    run = Locked(prs=[_done("feature/locked")])
    plan = _plan(repo, run)
    problems = cleanup.apply_plan(plan, repo, run)
    assert any("could not remove" in p and "delete" in p for p in problems)


# --- local branches ------------------------------------------------------------------


def test_branches_never_include_develop_main_or_current(repo: Path) -> None:
    _git(repo, "branch", "feature/merged")
    _git(repo, "switch", "-q", "-c", "current")
    plan = _plan(repo, Recorder(prs=[]))
    assert "feature/merged" in plan.branches
    for keep in ("develop", "main", "current"):
        assert keep not in plan.branches


def test_unmerged_branch_is_never_selected(repo: Path) -> None:
    _git(repo, "switch", "-q", "-c", "feature/unmerged")
    _commit(repo, "u.txt")
    _git(repo, "switch", "-q", "develop")
    plan = _plan(repo, Recorder(prs=[]))
    assert "feature/unmerged" not in plan.branches


def test_pr_fetch_branch_selected_only_when_pr_is_done(repo: Path) -> None:
    for n in (5, 6):
        _git(repo, "switch", "-q", "-c", f"pr-{n}")
        _commit(repo, f"pr{n}.txt")
    _git(repo, "switch", "-q", "develop")
    prs = [
        {"headRefName": "x", "state": "CLOSED", "number": 5, "isCrossRepository": True},
        {"headRefName": "y", "state": "OPEN", "number": 6, "isCrossRepository": True},
    ]
    plan = _plan(repo, Recorder(prs=prs))
    assert "pr-5" in plan.branches
    assert "pr-6" not in plan.branches


# --- remote branches -----------------------------------------------------------------


def _push_branch(repo: Path, name: str) -> None:
    _git(repo, "push", "-q", "origin", f"develop:refs/heads/{name}")
    _git(repo, "fetch", "-q", "origin")


def test_remote_branches_only_with_flag_and_only_safe_ones(repo: Path) -> None:
    for name in ("feature/merged", "feature/reopened", "fork-thing"):
        _push_branch(repo, name)
    prs = [
        {
            "headRefName": "feature/merged",
            "state": "MERGED",
            "number": 1,
            "isCrossRepository": False,
        },
        {
            "headRefName": "feature/reopened",
            "state": "MERGED",
            "number": 2,
            "isCrossRepository": False,
        },
        {
            "headRefName": "feature/reopened",
            "state": "OPEN",
            "number": 3,
            "isCrossRepository": False,
        },
        {"headRefName": "fork-thing", "state": "MERGED", "number": 4, "isCrossRepository": True},
        {"headRefName": "develop", "state": "MERGED", "number": 9, "isCrossRepository": False},
    ]
    assert _plan(repo, Recorder(prs=prs)).remote_branches == []
    run = Recorder(prs=prs)
    plan = _plan(repo, run, remote=True)
    assert plan.remote_branches == ["feature/merged"]
    assert cleanup.apply_plan(plan, repo, run) == []
    assert "feature/merged" not in _git(repo, "ls-remote", "--heads", "origin")


def test_a_merged_pr_branch_with_later_unmerged_commits_is_kept_on_origin(repo: Path) -> None:
    """A merged PR says nothing about commits pushed to its branch afterwards; deleting
    the branch would delete them."""
    _git(repo, "switch", "-q", "-c", "feature/reused")
    _commit(repo, "after-merge")
    _git(repo, "push", "-q", "origin", "feature/reused")
    _git(repo, "switch", "-q", "develop")
    _git(repo, "fetch", "-q", "origin")
    prs = [
        {
            "headRefName": "feature/reused",
            "state": "MERGED",
            "number": 5,
            "isCrossRepository": False,
        },
    ]
    assert _plan(repo, Recorder(prs=prs), remote=True).remote_branches == []


# --- stray .env / basetemp / agentctl / flow ------------------------------------------


def test_stray_env_in_kept_worktree_is_reported_never_deleted(repo: Path) -> None:
    """A kept worktree is in use; its .env is gflow's per-directory config and may hold
    credentials someone typed — the sweep names it, the owner decides."""
    wt = _unmerged_worktree(repo, "feature/kept")
    (wt / ".env").write_text("K=1", encoding="utf-8")
    run = Recorder(prs=[])
    plan = _plan(repo, run)
    assert [p.resolve() for p in plan.envs] == [(wt / ".env").resolve()]
    cleanup.apply_plan(plan, repo, run)
    assert (wt / ".env").read_text(encoding="utf-8") == "K=1"


def test_tracked_env_is_not_stray(repo: Path) -> None:
    wt = _unmerged_worktree(repo, "feature/tracked")
    _commit(wt, ".env")
    assert _plan(repo, Recorder(prs=[])).envs == []


def test_only_old_bt_temp_dirs_are_selected(repo: Path, tmp_path: Path) -> None:
    temps = tmp_path / "temps"
    old, fresh, other = temps / "btcl1", temps / "btcl2", temps / "keepme"
    for d in (old, fresh, other):
        d.mkdir(parents=True)
    for d in (old, other):
        os.utime(d, (time.time() - 7200, time.time() - 7200))
    plan = _plan(repo, Recorder(prs=[]), tmp_root=temps)
    assert plan.temps == [old]
    cleanup.apply_plan(plan, repo, Recorder(prs=[]))
    assert not old.exists() and fresh.exists() and other.exists()


def test_a_bt_dir_with_a_recent_child_is_in_use(repo: Path, tmp_path: Path) -> None:
    """Under xdist only `popen-gw*` children change; the parent's mtime stays old."""
    temps = tmp_path / "temps"
    busy = temps / "btcl9"
    (busy / "popen-gw0").mkdir(parents=True)
    os.utime(busy, (time.time() - 7200, time.time() - 7200))
    assert _plan(repo, Recorder(prs=[]), tmp_root=temps).temps == []


def test_remote_deletion_is_refused_when_the_fetch_failed(repo: Path) -> None:
    """A stale origin/<name> cannot prove its tip is in the base."""

    class Offline(Recorder):
        def __call__(
            self, cmd: list[str], cwd: Path | None = None
        ) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["git", "-C"] and "fetch" in cmd:
                self.calls.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 128, "", "could not resolve host")
            return super().__call__(cmd, cwd)

    _push_branch(repo, "feature/merged")
    run = Offline(prs=[_done("feature/merged")])
    rc = cleanup.main(["--repo", str(repo), "--remote", "--apply"], run=run)
    assert rc != 0
    assert "feature/merged" in _git(repo, "ls-remote", "--heads", "origin")


def test_agentctl_dead_agents_and_their_leases_are_reported(repo: Path, tmp_path: Path) -> None:
    script = tmp_path / "agentctl.py"
    script.write_text("", encoding="utf-8")
    out = (
        "\nAGENTS\n"
        "  claude-1  claude pid=1 alive  develop  C:/x\n"
        "  codex-2  codex pid=2 DEAD  feat  C:/y\n"
        "\nLEASES\n"
        "  app-port:8001                    codex-2\n"
        "  database:gflow                   claude-1\n"
    )
    plan = _plan(repo, Recorder(prs=[], agentctl_out=out), agentctl=script)
    text = "\n".join(plan.agents)
    assert "codex-2" in text and "app-port:8001" in text
    assert "claude-1" not in text
    assert "leave --id codex-2 --force" in text


def test_report_carries_the_flow_reminder(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cleanup.main(["--repo", str(repo), "--no-fetch"], run=Recorder(prs=[]), tmp_root=repo.parent)
    out = capsys.readouterr().out
    assert "Flow" in out and "dry run" in out.lower()
