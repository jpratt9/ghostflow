#!/usr/bin/env python3
"""Fail when a pytest run executed fewer tests than the floor.

A green build that ran nothing is not green: a collection error, a bad marker
expression, or an accidental `-k` filter can skip most of the suite while the
job still exits 0. This gate parses the junit XML pytest wrote and requires a
minimum number of EXECUTED tests (collected minus skipped).

Usage:
    python scripts/ci/check_test_count.py <junit-xml>... <min-executed>

Several reports are summed against one floor: ci.yml shards the 3.13 suite, and
the floor covers the whole suite, not each shard. A named report that is missing
fails the gate rather than quietly dropping out of the sum.

Floors are deliberately well below the real counts so routine test deletions
never trip them — they exist to catch collapse, not drift.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3 or not sys.argv[-1].isdigit():
        print("usage: check_test_count.py <junit-xml>... <min-executed>")
        return 2
    reports, floor = [Path(p) for p in sys.argv[1:-1]], int(sys.argv[-1])
    missing = [str(p) for p in reports if not p.is_file()]
    if missing:
        print(f"FAIL: missing junit report(s): {', '.join(missing)} (a shard that ran nothing)")
        return 1
    # iter() is self-inclusive, so this handles both a <testsuites> wrapper and
    # a bare <testsuite> root with one expression.
    suites = [s for p in reports for s in ET.parse(p).getroot().iter("testsuite")]
    collected = sum(int(suite.get("tests", "0")) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
    errors = sum(int(suite.get("errors", "0")) for suite in suites)
    # An errored test never ran its body — it must not count as executed
    # (matters the day someone masks pytest's own exit code).
    executed = collected - skipped - errors
    print(
        f"executed={executed} (collected={collected}, skipped={skipped}, "
        f"errors={errors}), floor={floor}"
    )
    if executed < floor:
        print(
            f"FAIL: only {executed} tests executed but the floor is {floor} — "
            "a green build that ran nothing is not green. Check for collection "
            "errors, marker/-k filters, or a broken conftest.",
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
