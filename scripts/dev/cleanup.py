"""Report — and with ``--apply`` remove — what a release or takeover session leaves behind.

Dry run by default: prints what it WOULD remove and mutates nothing. Never prompts.

    uv run python scripts/dev/cleanup.py                  # dry run
    uv run python scripts/dev/cleanup.py --apply          # remove local leftovers
    uv run python scripts/dev/cleanup.py --apply --remote # + merged origin branches

Categories: worktrees (PR merged/closed, or detached inside the base; never the main
checkout, a dirty or a locked one — ancestry alone is not "finished", a fresh branch is an
ancestor too), local branches (merged, plus ``pr-<N>`` fetch branches whose PR is done),
remote branches (``--remote`` only: PR merged, same repo, no open PR, tip contained in the
base; refused if the fetch failed), old ``bt*`` pytest basetemp dirs, and — report only —
untracked ``.env`` files in kept worktrees, dead agentctl agents and a Flow-side reminder.

Stdlib only; ``git``/``gh`` through one ``run`` seam so tests can fake ``gh``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Runner = Callable[..., "subprocess.CompletedProcess[str]"]

PROTECTED = {"develop", "main"}
AGENTCTL = Path.home() / ".agents" / "skills" / "multi-agent-dev" / "scripts" / "agentctl.py"
FLOW_REMINDER = (
    "Flow (report only): gflow has no project or scene delete, and `character rm` is not "
    "ported to flow.google.com — remove e2e/spike projects, scenes and characters by hand in "
    "the Flow UI if they matter. (e2e titles share no common prefix, so none are listed.)"
)


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


@dataclass
class Plan:
    worktrees: list[tuple[Path, str]] = field(default_factory=lambda: [])
    kept: list[tuple[Path, str]] = field(default_factory=lambda: [])
    branches: list[str] = field(default_factory=lambda: [])
    remote_branches: list[str] = field(default_factory=lambda: [])
    envs: list[Path] = field(default_factory=lambda: [])
    temps: list[Path] = field(default_factory=lambda: [])
    agents: list[str] = field(default_factory=lambda: [])
    remote_checked: bool = False


def _git(run: Runner, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *args])


def _lines(run: Runner, repo: Path, *args: str) -> list[str]:
    return [ln for ln in _git(run, repo, *args).stdout.splitlines() if ln.strip()]


def _is_ancestor(run: Runner, repo: Path, rev: str, base: str) -> bool:
    return _git(run, repo, "merge-base", "--is-ancestor", rev, base).returncode == 0


def _prs(run: Runner, repo: Path) -> list[dict[str, object]]:
    """Every PR's head/state/number, or [] when gh is missing or fails (skip silently)."""
    fields = "headRefName,state,number,isCrossRepository"
    try:
        out = run(
            ["gh", "pr", "list", "--state", "all", "--limit", "1000", "--json", fields], cwd=repo
        )
    except FileNotFoundError:
        return []
    if out.returncode != 0:
        return []
    return json.loads(out.stdout or "[]")


def _worktrees(run: Runner, repo: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in _git(run, repo, "worktree", "list", "--porcelain").stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "worktree":
            entries.append({"path": value})
        elif entries and key:
            entries[-1][key] = value
    return entries


def _agent_report(run: Runner, repo: Path, agentctl: Path | None) -> list[str]:
    if agentctl is None or not agentctl.exists():
        return []
    out = run([sys.executable, str(agentctl), "--cwd", str(repo), "status"]).stdout
    section, dead, leases = "", [], []
    for line in out.splitlines():
        if line.strip() in ("AGENTS", "LEASES"):
            section = line.strip()
        elif section == "AGENTS" and " DEAD " in f"{line} ":
            dead.append(line.split()[0])
        elif section == "LEASES" and line.strip():
            key, *holders = line.split()
            holders = [h.rstrip(",") for h in holders]
            leases += [f"{key} held by {h}" for h in holders if h in dead]
    report = [f"dead agent {a} — `python {agentctl} leave --id {a} --force`" for a in dead]
    return report + [f"lease {lease} (dead)" for lease in leases]


def build_plan(
    repo: Path,
    *,
    base: str,
    run: Runner,
    remote: bool,
    tmp_root: Path,
    older_than_hours: float,
    agentctl: Path | None,
) -> Plan:
    plan = Plan(remote_checked=remote)
    prs = _prs(run, repo)
    open_heads = {p["headRefName"] for p in prs if p["state"] == "OPEN"}
    done_heads = {p["headRefName"] for p in prs if p["state"] in ("MERGED", "CLOSED")} - open_heads
    done_numbers = {p["number"] for p in prs if p["state"] in ("MERGED", "CLOSED")}

    here = Path(_git(run, repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    remaining_branches: set[str] = set()
    for i, wt in enumerate(_worktrees(run, repo)):
        path = Path(wt["path"])
        branch = wt.get("branch", "").removeprefix("refs/heads/")
        if i == 0 or path.resolve() == here or not path.exists():
            remaining_branches.add(branch)
            continue
        # Ancestry alone is not "finished": a worktree an agent just branched from the base
        # is an ancestor too. Only a done PR (or a detached checkout of the base) says so.
        if branch in done_heads:
            why = "PR merged/closed"
        elif "detached" in wt and _is_ancestor(run, repo, wt["HEAD"], base):
            why = "detached, in base"
        else:
            why = ""
        dirty = bool(_git(run, path, "status", "--porcelain").stdout.strip())
        if why and not dirty and "locked" not in wt:
            plan.worktrees.append((path, f"{branch or 'detached'}: {why}"))
            continue
        remaining_branches.add(branch)
        plan.kept.append((path, "locked" if "locked" in wt else "dirty" if why else "in use"))
        env = path / ".env"
        if env.is_file() and not _git(run, path, "ls-files", ".env").stdout.strip():
            plan.envs.append(env)

    current = _git(run, repo, "branch", "--show-current").stdout.strip()
    skip = PROTECTED | remaining_branches | {current}
    merged = set(_lines(run, repo, "branch", "--merged", base, "--format=%(refname:short)"))
    for name in _lines(run, repo, "for-each-ref", "refs/heads", "--format=%(refname:short)"):
        pr = re.fullmatch(r"pr-(\d+)", name)
        if name not in skip and (name in merged or (pr and int(pr.group(1)) in done_numbers)):
            plan.branches.append(name)

    if remote:
        on_origin = set(
            _lines(run, repo, "for-each-ref", "refs/remotes/origin", "--format=%(refname:lstrip=3)")
        )
        merged_heads = {
            str(p["headRefName"])
            for p in prs
            if p["state"] == "MERGED" and not p["isCrossRepository"]
        }
        # A merged PR says nothing about commits pushed to its branch afterwards: the
        # origin tip must itself be contained in the base, or deleting it loses them.
        plan.remote_branches = sorted(
            name
            for name in (merged_heads & on_origin) - open_heads - PROTECTED - {"HEAD"}
            if _is_ancestor(run, repo, f"origin/{name}", base)
        )

    cutoff = time.time() - older_than_hours * 3600
    plan.temps = sorted(d for d in tmp_root.glob("bt*") if d.is_dir() and _newest(d) < cutoff)
    plan.agents = _agent_report(run, repo, agentctl)
    return plan


def _newest(d: Path) -> float:
    """Newest mtime of a dir and its direct children: under xdist only `popen-gw*` change."""
    return max([d.stat().st_mtime, *(c.stat().st_mtime for c in d.iterdir())])


def apply_plan(plan: Plan, repo: Path, run: Runner) -> list[str]:
    """Perform the plan; return problems instead of raising (a Windows .venv lock is normal)."""
    problems: list[str] = []
    for path, _ in plan.worktrees:
        if _git(run, repo, "worktree", "remove", "--force", str(path)).returncode != 0:
            problems.append(f"could not remove {path} (a file is in use?) — delete {path} later")
    if plan.worktrees:
        _git(run, repo, "worktree", "prune")
    for name in plan.branches:
        out = _git(run, repo, "branch", "-D", name)
        if out.returncode != 0:
            problems.append(f"branch {name}: {out.stderr.strip()}")
    for name in plan.remote_branches:
        out = _git(run, repo, "push", "origin", "--delete", name)
        if out.returncode != 0:
            problems.append(f"origin/{name}: {out.stderr.strip()}")
    for d in plan.temps:
        shutil.rmtree(d, ignore_errors=True)
    return problems


def render(plan: Plan, *, applied: bool, base: str) -> str:
    verb = "Removed" if applied else "Would remove"
    out = [f"cleanup — {'APPLIED' if applied else 'dry run (pass --apply to remove)'}; base {base}"]

    def group(title: str, items: list[str]) -> None:
        out.append(f"\n{title} ({len(items)})")
        out.extend(f"  {i}" for i in items)

    group(f"{verb}: worktrees", [f"{p}  [{why}]" for p, why in plan.worktrees])
    group("Kept: worktrees", [f"{p}  [{why}]" for p, why in plan.kept])
    group(f"{verb}: local branches", plan.branches)
    if plan.remote_checked:
        group(f"{verb}: origin branches", plan.remote_branches)
    else:
        out.append("\nOrigin branches: not checked (pass --remote)")
    # Kept worktrees are in use, and a .env may hold credentials someone typed: name it only.
    group("Untracked .env in kept worktrees (report only)", [str(p) for p in plan.envs])
    group(f"{verb}: pytest basetemp dirs", [str(p) for p in plan.temps])
    group("agentctl (report only)", plan.agents)
    out.append(f"\n{FLOW_REMINDER}")
    return "\n".join(out)


def main(
    argv: list[str] | None = None,
    *,
    run: Runner = _run,
    tmp_root: Path | None = None,
    agentctl: Path | None = AGENTCTL,
) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="repository to clean (default: cwd)"
    )
    ap.add_argument(
        "--base", default="origin/develop", help="merge target (default: origin/develop)"
    )
    ap.add_argument("--apply", action="store_true", help="perform the removals")
    ap.add_argument(
        "--remote", action="store_true", help="also delete merged same-repo branches on origin"
    )
    ap.add_argument("--no-fetch", action="store_true", help="skip `git fetch --prune`")
    ap.add_argument(
        "--older-than", type=float, default=1.0, help="basetemp age in hours (default 1)"
    )
    args = ap.parse_args(argv)

    repo: Path = args.repo.resolve()
    if not args.no_fetch and _git(run, repo, "fetch", "--prune", "origin").returncode != 0:
        if args.remote:
            # A stale origin/<name> cannot prove its tip is in the base.
            print("! git fetch failed — refusing --remote; rerun when origin is reachable")
            return 2
        print("! git fetch failed — judging against the last fetched origin")
    plan = build_plan(
        repo,
        base=args.base,
        run=run,
        remote=args.remote,
        tmp_root=tmp_root if tmp_root is not None else Path(tempfile.gettempdir()),
        older_than_hours=args.older_than,
        agentctl=agentctl,
    )
    problems = apply_plan(plan, repo, run) if args.apply else []
    print(render(plan, applied=args.apply, base=args.base))
    for p in problems:
        print(f"! {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
