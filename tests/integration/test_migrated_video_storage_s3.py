"""#1003: a flow.google.com clip lands in the configured S3 bucket (RustFS in Docker).

Run with Docker and the ``containers`` dependency group::

    uv run --group containers pytest -m containers tests/integration/
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.containers]

_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@pytest.mark.asyncio
async def test_migrated_download_uploads_the_clip_to_s3(
    s3_storage_uri: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The migrated arm's download, wired to the transport's one writer, puts the
    clip's exact bytes in the bucket and nothing on local disk."""
    from gflow_cli.api.transports.batchexecute import GenerationRecord
    from gflow_cli.api.transports.migrated_composer import MigratedComposer
    from gflow_cli.api.transports.ui_automation import UiAutomationTransport
    from gflow_cli.storage import is_cloud_path

    monkeypatch.chdir(tmp_path)
    transport = UiAutomationTransport()
    transport._storage_uri = s3_storage_uri  # noqa: SLF001
    monkeypatch.setattr(MigratedComposer, "fetch_mp4", AsyncMock(return_value=_MP4))
    record = GenerationRecord(
        workflow_id="wf1",
        project_id="p1",
        media_id="m1003-s3",
        status=3,
        video_url="https://flow-content.google/x.mp4",
    )

    path = await MigratedComposer().download(
        MagicMock(),
        record,
        partial(transport._save_clip, out_dir=None),  # noqa: SLF001
    )

    assert path is not None and is_cloud_path(path)
    assert str(path).startswith(s3_storage_uri)
    assert path.read_bytes() == _MP4
    assert not (tmp_path / "tmp").exists()
