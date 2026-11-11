#!/usr/bin/env python3
"""Advisory check for what a change silently stops existing (#713).

Two signals on ``git diff <base>...HEAD``, both invisible when reading a diff:

  A. A Markdown doc (under ``docs/`` or at the repo root) whose deletions exceed
     its insertions by more than 50 lines AND more than 3x — a gutted file still
     passes every link and hygiene gate.
  B. A deleted path (file, or a directory that no longer exists at HEAD) still
     referenced from a tracked text file — e.g. a workflow ``paths:``
     entry that would quietly stop matching anything. ``CHANGELOG.md`` is
     ignored: history legitimately names removed paths.

ALWAYS exits 0 — a genuine removal is legitimate and the author says so in the
PR. Exit 2 only on a usage error (an unresolvable base ref). Findings go to
stdout, as ``::warning::`` annotations, and to ``$GITHUB_STEP_SUMMARY`` if set.

Run manually:
    uv run python scripts/ci/check_deletions.py --base origin/develop
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

MIN_NET_DELETIONS = 50
MIN_RATIO = 3
_ERE_SPECIAL = set(".[]()*+?{}|^$\\")
_NOT_PATH_CHAR_BEFORE = "(^|[^[:alnum:]_.-])"
_NOT_PATH_CHAR_AFTER = "($|[^[:alnum:]_-])"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout


def _is_doc(path: str) -> bool:
    return path.endswith(".md") and (path.startswith("docs/") or "/" not in path)


def gutted_docs(base: str) -> list[str]:
    findings: list[str] = []
    for row in _git("diff", "--numstat", "--no-renames", f"{base}...HEAD").splitlines():
        added, deleted, path = row.split("\t", 2)
        if added == "-" or not _is_doc(path):  # "-" = binary
            continue
        ins, dels = int(added), int(deleted)
        if dels - ins > MIN_NET_DELETIONS and dels > MIN_RATIO * ins:
            findings.append(
                f"{path}: -{dels}/+{ins} lines — deletions far exceed insertions; "
                "confirm the removal is intended"
            )
    return findings


def orphaned_references(base: str) -> list[str]:
    deleted = _git(
        "diff", "--name-only", "--no-renames", "--diff-filter=D", f"{base}...HEAD"
    ).splitlines()
    head_files = _git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
    head_dirs = {f.rsplit("/", i)[0] for f in head_files for i in range(1, f.count("/") + 1)}
    gone_dirs: set[str] = set()
    for path in deleted:
        parts = path.split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            d = "/".join(parts[:depth])
            if d not in head_dirs:
                gone_dirs.add(d)
                break  # the outermost gone directory covers the ones below it
    # A file inside a gone directory is found by searching for the directory. A
    # top-level directory is searched as `name/`: the bare word (`eval`) matches prose.
    needles = [d if "/" in d else d + "/" for d in sorted(gone_dirs)] + [
        p for p in deleted if not any(p.startswith(d + "/") for d in gone_dirs)
    ]
    findings: list[str] = []
    for needle in needles:
        # Path boundaries, so `scripts/autopilot` matches `"/scripts/autopilot"` but not
        # `myscripts/autopilot` or `scripts/autopilot2`.
        pattern = _NOT_PATH_CHAR_BEFORE + "".join(
            "\\" + c if c in _ERE_SPECIAL else c for c in needle
        )
        if not needle.endswith("/"):
            pattern += _NOT_PATH_CHAR_AFTER
        hits = subprocess.run(
            ["git", "grep", "-n", "-I", "-E", "-e", pattern, "--", ".", ":(exclude)CHANGELOG.md"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        for hit in hits.splitlines():
            file, line, _ = hit.split(":", 2)
            findings.append(f"{file}:{line}: still references deleted path `{needle}`")
    return findings


def _report(gutted: list[str], orphaned: list[str]) -> str:
    lines = ["## 🗑️ Deletion advisory (non-blocking)", ""]
    if not gutted and not orphaned:
        return "\n".join([*lines, "No gutted docs and no references to deleted paths."])
    if gutted:
        lines += ["**Docs with far more deletions than insertions:**", ""]
        lines += [f"- {f}" for f in gutted] + [""]
    if orphaned:
        lines += ["**References to deleted paths:**", ""]
        lines += [f"- {f}" for f in orphaned] + [""]
    lines.append("_Advisory only — if the removal is intended, say so in the PR._")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base ref to diff against")
    args = parser.parse_args(argv)
    try:
        _git("rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}")
    except subprocess.CalledProcessError:
        print(f"check_deletions: cannot resolve base ref {args.base!r}")
        return 2

    gutted = gutted_docs(args.base)
    orphaned = orphaned_references(args.base)
    report = _report(gutted, orphaned)
    print(report)
    for finding in gutted + orphaned:
        print(f"::warning::{finding}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(report + "\n")
        except OSError:
            pass
    return 0  # ALWAYS advisory — never fail the build.


if __name__ == "__main__":
    sys.exit(main())
