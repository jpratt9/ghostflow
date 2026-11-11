r"""#1114: does the ``-o`` relocation survive a REAL second filesystem? ($0 — no browser)

The PR's tests fake EXDEV by patching ``os.rename``/``os.replace``. This runs the
production code on two real mounts, plus the edge cases the council named.

Arms (each prints one JSON line; ``measured: false`` when its precondition is absent):
  A  control   ``Path.replace`` (the pre-fix line) from mount A to mount B
  B  cli       ``cli_video._relocate_video_output`` from mount A to mount B
  C  worker    ``FlowWorker.process_task`` (MCP queued t2v) moving A -> B
  D  overwrite ``_relocate_video_output`` onto an EXISTING target (same mount and A -> B)
  E  dir       the MCP worker with ``output_file`` naming an existing DIRECTORY

PRE-REGISTERED READING:
  * A raises errno 18 (EXDEV), B and C land the bytes and remove the source
    -> the root cause is real on a real kernel and the fix holds there
  * A succeeds -> the mounts are not distinct; nothing about #1114 is measured
  * B or C raises -> the fix is wrong; the PR does not ship
  * D replaces the target bytes on every arm -> overwrite behaviour is preserved
  * E: whatever happens is recorded as-is; it decides whether the MCP edge needs a guard

Linux, two mounts (the reporter's shape):
    docker run --rm --tmpfs /mnt/a -v <repo>:/src:ro python:3.12-slim sh -c \
      "cp -r /src /work && pip install -q /work && \
       python /work/scripts/dev/spike_1114_cross_device_relocate.py --a /mnt/a --b /work/out"
Windows, two volumes (any mapped drive, e.g. an SMB share; delete the folder after):
    uv run python scripts/dev/spike_1114_cross_device_relocate.py --a tmp/a --b D:/gflow-spike-1114
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from gflow_cli.api.video import VideoResult, VideoStatus
from gflow_cli.cli_video import _relocate_video_output  # pyright: ignore[reportPrivateUsage]
from gflow_cli.data.store import DataStore
from gflow_cli.worker.daemon import FlowWorker
from gflow_cli.worker.queue import QueueRepository

_OK = "MEDIA_GENERATION_STATUS_SUCCESSFUL"


def _emit(arm: str, **fields: object) -> None:
    print(json.dumps({"arm": arm, "os": platform.system(), **fields}, default=str))


def _clip(directory: Path, name: str, data: bytes = b"clip") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


def _result(path: Path) -> VideoResult:
    return VideoResult(status=VideoStatus(media_id="m", status=_OK), local_path=path)


def arm_control(a: Path, b: Path) -> None:
    src = _clip(a, "control.mp4")
    try:
        src.replace(b / "control.mp4")
        _emit("A-control", raised=None)
    except OSError as exc:
        _emit("A-control", raised=type(exc).__name__, errno=exc.errno)


def arm_cli(a: Path, b: Path) -> None:
    src = _clip(a, "cli.mp4")
    target = b / "cli" / "out.mp4"
    try:
        out = _relocate_video_output(_result(src), target)
        _emit(
            "B-cli",
            landed=target.read_bytes() == b"clip",
            source_left=src.exists(),
            local_path=out.local_path,
        )
    except OSError as exc:
        _emit("B-cli", raised=type(exc).__name__, errno=exc.errno)


class _FakeClient:
    def __init__(self, result: VideoResult) -> None:
        self.generate_video = AsyncMock(return_value=result)
        self.create_project = AsyncMock()

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _run_worker(src: Path, output_file: Path, db_dir: Path, task_id: str) -> dict[str, object]:
    store = DataStore.open(db_dir / f"{task_id}.db")
    store.conn.execute(
        "INSERT INTO profiles(name, profile_dir, first_seen_at) "
        "VALUES ('default', '/p', '2026-10-29T00:00:00Z')"
    )
    repo = QueueRepository(store)
    task = repo.enqueue_task(
        task_id=task_id,
        profile_name="default",
        task_type="t2v",
        payload={"prompt": "p", "aspect": "16:9", "output_file": str(output_file)},
    )
    worker = FlowWorker("default", str(store.path))
    with patch("gflow_cli.worker.daemon.FlowApiClient", return_value=_FakeClient(_result(src))):
        asyncio.run(worker.process_task(task))
    row = repo.get_task(task_id)
    worker.close()
    store.close()
    assert row is not None
    return {"status": row.status, "error": row.error, "source_left": src.exists()}


def arm_worker(a: Path, b: Path, db_dir: Path) -> None:
    src = _clip(a, "worker.mp4")
    target = b / "worker" / "out.mp4"
    fields = _run_worker(src, target, db_dir, "spike-worker")
    _emit("C-worker", landed=target.exists() and target.read_bytes() == b"clip", **fields)


def arm_overwrite(a: Path, b: Path) -> None:
    for label, src_dir in (("same-mount", b), ("cross-mount", a)):
        target = _clip(b / "ow", f"{label}.mp4", b"OLD")
        src = _clip(src_dir / "ow-src", f"{label}.mp4", b"NEW")
        try:
            _relocate_video_output(_result(src), target)
            _emit(
                f"D-overwrite-{label}",
                target=target.read_bytes().decode(),
                source_left=src.exists(),
            )
        except OSError as exc:
            _emit(f"D-overwrite-{label}", raised=type(exc).__name__, errno=exc.errno)


def arm_dir(a: Path, b: Path, db_dir: Path) -> None:
    src = _clip(a, "dir.mp4")
    out_dir = b / "existing_dir"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = _run_worker(src, out_dir, db_dir, "spike-dir")
    _emit("E-dir", inside=(out_dir / "dir.mp4").exists(), **fields)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=Path, required=True, help="source mount (download dir)")
    parser.add_argument("--b", type=Path, required=True, help="target mount (-o)")
    args = parser.parse_args()
    a, b = args.a.resolve(), args.b.resolve()
    a.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)
    distinct = os.stat(a).st_dev != os.stat(b).st_dev
    _emit("mounts", a=a, b=b, distinct=distinct)
    with tempfile.TemporaryDirectory() as db:
        if distinct:
            arm_control(a, b)
            arm_cli(a, b)
            arm_worker(a, b, Path(db))
        else:
            _emit("A/B/C", measured=False, reason="a and b share a device")
        arm_overwrite(a, b)
        arm_dir(a, b, Path(db))


if __name__ == "__main__":
    main()
