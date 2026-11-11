"""#1091: an output path gflow cannot write is a classified error, not "Unexpected error".

The raw ``OSError`` from ``storage._write_local`` used to reach the CLI's catch-all, which
told the user to file a bug for a run that had generated fine (#1035 salvaged it).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gflow_cli.errors import EXIT_CODE_MAP, ConfigurationError, is_retryable
from gflow_cli.storage import write_asset_async


def test_an_unwritable_output_path_raises_a_classified_error(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_bytes(b"x")  # mkdir of a child fails with an OSError on every OS
    target = blocker / "sub" / "image.png"

    with pytest.raises(ConfigurationError) as info:
        asyncio.run(write_asset_async(target, b"png"))

    err = info.value
    assert isinstance(err.__cause__, OSError)
    assert err.detail.startswith("Could not write the output file (")
    assert str(tmp_path) not in err.detail  # the detail is persisted to the catalog
    assert "--out" in err.remediation_hint
    assert next(c for cls, c in EXIT_CODE_MAP.items() if isinstance(err, cls)) == 11
    assert not is_retryable(err)
