"""Upload a local reference into a project once, then mention it in place (#772).

flow.google.com uploaded every local ``--ref`` again on every call, so a loop over one
character image filled the project's library with copies of it. Here an upload is
recorded in the catalog, and a later run in the same project that names the same file
(same path, same bytes) mentions the recorded image instead. Shared by the CLI and the
MCP worker, which build the request the same way.

Where the host has no in-place upload (labs: the transport answers ``None``), a file not
recorded in the project is left for the editor's media dialog, which dedups by file name
itself (#314). A recorded one is referenced in place on either host.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import structlog

from gflow_cli.api.client import MAX_IMAGE_BYTES
from gflow_cli.api.dto import AssetInfo
from gflow_cli.api.image import ImageRef, recorded_in_project
from gflow_cli.errors import DataStoreError, ReferenceNotFoundError

if TYPE_CHECKING:
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.dto import ProjectInfo
    from gflow_cli.api.image import GenerateImageRequest
    from gflow_cli.data.recorder import OperationRecorder

log = structlog.get_logger("reference_uploads")

T = TypeVar("T")


async def generate_reusing_uploads(
    client: FlowApiClient,
    request: GenerateImageRequest,
    *,
    recorder: OperationRecorder,
    profile_name: str,
    profile_dir: Path,
    project: ProjectInfo,
    generate: Callable[[GenerateImageRequest], Awaitable[T]],
) -> tuple[T, GenerateImageRequest]:
    """Run ``generate`` with each local reference uploaded once, and return the request used.

    A recorded image deleted from the project since raises ``ReferenceNotFoundError``
    before anything is submitted; its file is then uploaded again (and recorded, so the
    next run reuses the new copy) and the generation is tried once more.
    """
    if not request.ref_paths:
        return await generate(request), request

    async def upload(path: Path) -> ImageRef | None:
        return await _upload(client, recorder, profile_name, profile_dir, project, path)

    reused: dict[str, Path] = {}
    refs: list[ImageRef] = []
    paths: list[Path] = []
    for path in request.ref_paths:
        ref = _recorded_upload(recorder, profile_name, path, project.project_id)
        if ref is not None:
            reused[ref.name] = path
        else:
            ref = await upload(path)
        if ref is None:
            paths.append(path)
        else:
            refs.append(ref)
    request = dataclasses.replace(request, refs=(*request.refs, *refs), ref_paths=tuple(paths))
    try:
        return await generate(request), request
    except ReferenceNotFoundError as exc:
        # Only a miss that names an image this run reused; any other (a character, a
        # chip out of order) would fail the same way again after a needless upload.
        if not any(media_id in str(exc.detail) for media_id in reused):
            raise
    log.info("reference_uploads.recorded_image_gone", count=len(reused), issue_ref="#772")
    fresh: list[ImageRef] = []
    for ref in request.refs:
        path = reused.get(ref.name)
        new = await upload(path) if path is not None else None
        fresh.append(new or ref)
    request = dataclasses.replace(request, refs=tuple(fresh))
    return await generate(request), request


def _recorded_upload(
    recorder: OperationRecorder, profile_name: str, path: Path, project_id: str
) -> ImageRef | None:
    """The image this project already holds for this file, or ``None``."""
    try:
        resolved = path.resolve()
        if resolved.stat().st_size > MAX_IMAGE_BYTES:
            return None  # validate_image_file refuses it at upload; do not hash it first
        sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
        repo = recorder.repository
        # shortcut: only the newest record of this file is checked; a copy uploaded to
        # this project before a newer one elsewhere is uploaded again. Fine for the
        # one-project loops #772 reports; walk all records if projects get interleaved.
        seed = repo.resolve_seed_image_by_file(profile_name, resolved, sha256)
        if seed is None or not recorded_in_project(seed.flow_project_id, project_id):
            return None
        asset = repo.get_asset_by_flow_media_id(profile_name, seed.flow_media_id)
    except (DataStoreError, OSError) as exc:
        log.debug("reference_uploads.lookup_skipped", error=str(exc)[:120])
        return None
    name = asset.metadata_json.get("display_name") if asset is not None else None
    if not isinstance(name, str) or not name:
        return None  # flow.google.com finds an in-place reference by its caption
    log.info("reference_uploads.reused", media_id=seed.flow_media_id, issue_ref="#772")
    return ImageRef(
        name=seed.flow_media_id,
        display_name=name,
        local_path=str(resolved),
        local_sha256=sha256,
        in_project=True,
    )


async def _upload(
    client: FlowApiClient,
    recorder: OperationRecorder,
    profile_name: str,
    profile_dir: Path,
    project: ProjectInfo,
    path: Path,
) -> ImageRef | None:
    try:
        ref = await client.upload_reference_in_place(project.project_id, path)
    except (ValueError, FileNotFoundError):
        # A file the upload check refuses keeps the route it had before #772 (the
        # editor dialog on labs, the composer upload on flow.google.com).
        return None
    if ref is None:
        return None
    asset = AssetInfo(
        name=ref.name,
        project_id=project.project_id,
        workflow_id="",
        display_name=ref.display_name,
        width=0,
        height=0,
    )
    try:
        recorder.record_upload_image(
            profile_name=profile_name,
            profile_dir=profile_dir,
            project=project,
            asset=asset,
            image_path=path,
        )
    except DataStoreError as exc:
        # The upload stands; only the reuse on a later run is lost.
        log.warning("reference_uploads.record_failed", media_id=ref.name, error=str(exc)[:120])
    return ref
