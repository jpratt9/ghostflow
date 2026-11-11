"""#772: a local --ref is uploaded into a project once, then referenced in place.

Each `image i2i` with the same `--ref` uploaded the file again on flow.google.com, so a
122-prompt loop left 122 copies in the project's library. The upload is now recorded,
and a later run in the same project mentions the recorded image instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gflow_cli.api.dto import ProjectInfo
from gflow_cli.api.image import GenerateImageRequest, ImageRef
from gflow_cli.config import get_settings
from gflow_cli.data.recorder import OperationRecorder
from gflow_cli.errors import ReferenceNotFoundError
from gflow_cli.services.reference_uploads import generate_reusing_uploads

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_PROJECT = ProjectInfo(project_id="11111111-1111-1111-1111-111111111111", title="p")
_OTHER = ProjectInfo(project_id="22222222-2222-2222-2222-222222222222", title="q")


class _Client:
    """Uploads in place like flow.google.com, or declines (None) like labs."""

    def __init__(self, *, in_place: bool = True) -> None:
        self.in_place = in_place
        self.uploads: list[Path] = []

    async def upload_reference_in_place(self, project_id: str, path: Path) -> ImageRef | None:
        if not self.in_place:
            return None
        self.uploads.append(path)
        n = len(self.uploads)
        return ImageRef(
            name=f"0000000{n}-0000-0000-0000-000000000000",
            display_name=f"ref-{n}.png",
            in_project=True,
        )


async def _run(
    client: _Client,
    ref: Path,
    project: ProjectInfo = _PROJECT,
    generate: Any = None,
) -> GenerateImageRequest:
    recorder = OperationRecorder.open(get_settings())
    seen: list[GenerateImageRequest] = []

    async def _generate(req: GenerateImageRequest) -> str:
        seen.append(req)
        return "ok"

    try:
        result, req = await generate_reusing_uploads(
            client,  # type: ignore[arg-type]
            GenerateImageRequest(prompt="a cup", ref_paths=(ref,)),
            recorder=recorder,
            profile_name="p1",
            profile_dir=Path("profile_p1"),
            project=project,
            generate=generate or _generate,
        )
    finally:
        recorder.close()
    assert result == "ok"
    return req


@pytest.fixture
def ref(tmp_path: Path) -> Path:
    path = tmp_path / "character.png"
    path.write_bytes(_PNG)
    return path


async def test_the_second_run_mentions_the_first_upload(ref: Path) -> None:
    client = _Client()
    first = await _run(client, ref)
    second = await _run(client, ref)

    assert len(client.uploads) == 1
    assert first.ref_paths == () and second.ref_paths == ()
    assert second.refs[0].name == first.refs[0].name
    assert second.refs[0].display_name == "ref-1.png"
    assert second.refs[0].in_project
    assert second.refs[0].local_path  # the #393 fallback file, kept for the retry


async def test_another_project_gets_its_own_upload(ref: Path) -> None:
    client = _Client()
    await _run(client, ref)
    other = await _run(client, ref, project=_OTHER)

    assert len(client.uploads) == 2
    assert other.refs[0].name.startswith("00000002")


async def test_changed_bytes_at_the_same_path_upload_again(ref: Path) -> None:
    client = _Client()
    await _run(client, ref)
    ref.write_bytes(_PNG + b"\x01")
    await _run(client, ref)

    assert len(client.uploads) == 2


async def test_labs_keeps_the_path_for_the_editor_dialog(ref: Path) -> None:
    client = _Client(in_place=False)
    req = await _run(client, ref)
    again = await _run(client, ref)

    assert req.ref_paths == (ref,) and req.refs == ()
    assert again.ref_paths == (ref,)


async def test_a_recorded_image_deleted_from_the_project_is_uploaded_again(ref: Path) -> None:
    client = _Client()
    await _run(client, ref)
    attempts: list[GenerateImageRequest] = []

    async def _generate(req: GenerateImageRequest) -> str:
        attempts.append(req)
        if len(attempts) == 1:
            raise ReferenceNotFoundError(
                detail=f"image {req.refs[0].name} is not in this project's grid"
            )
        return "ok"

    final = await _run(client, ref, generate=_generate)

    assert len(attempts) == 2
    assert attempts[0].refs[0].name.startswith("00000001")
    assert attempts[1].refs[0].name.startswith("00000002")
    assert final.refs[0].name.startswith("00000002")
    # The fresh copy is the one the next run reuses.
    nxt = await _run(client, ref)
    assert nxt.refs[0].name.startswith("00000002")
    assert len(client.uploads) == 2


async def test_a_miss_on_a_fresh_upload_is_not_retried(ref: Path) -> None:
    client = _Client()

    async def _generate(req: GenerateImageRequest) -> str:
        raise ReferenceNotFoundError(detail="did not attach")

    with pytest.raises(ReferenceNotFoundError):
        await _run(client, ref, generate=_generate)
    assert len(client.uploads) == 1


async def test_an_unrelated_miss_is_not_retried_with_a_new_upload(ref: Path) -> None:
    client = _Client()
    await _run(client, ref)
    attempts: list[GenerateImageRequest] = []

    async def _generate(req: GenerateImageRequest) -> str:
        attempts.append(req)
        raise ReferenceNotFoundError(detail="character 'Kael' did not attach as an entity")

    with pytest.raises(ReferenceNotFoundError):
        await _run(client, ref, generate=_generate)
    assert len(attempts) == 1
    assert len(client.uploads) == 1


async def test_a_file_the_upload_check_refuses_keeps_its_old_route(tmp_path: Path) -> None:
    class _Refusing(_Client):
        async def upload_reference_in_place(self, project_id: str, path: Path) -> ImageRef | None:
            raise ValueError("not an image")

    text = tmp_path / "notes.png"
    text.write_text("not an image", encoding="utf-8")
    req = await _run(_Refusing(), text)

    assert req.ref_paths == (text,) and req.refs == ()
