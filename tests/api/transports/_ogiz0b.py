"""A form-decoded ``ogiZ0b`` image submit body in the measured shape (#723).

Measured 2026-10-13 (``scripts/dev/spike_image_submit_references.py``): each request entry
carries its media references at index 2 and its character references at index 10.
"""

from __future__ import annotations

import json


def submit_body(
    media: tuple[str, ...] = (),
    entities: tuple[str, ...] = (),
    model: str = "BELUGA",
    project: str = "33333333-3333-4333-8333-333333333333",
    mentioned: tuple[str, ...] = (),
) -> str:
    """``mentioned`` ids appear only in the prompt document, as a media chip's id does."""
    entry: list[object] = [
        None,
        None,
        [[m, None, None, None, 1] for m in media] or None,
        12345,
        3,
        model,
        None,
        [None, 22, None, None, None, project],
        [
            [[None, [None, None, [i, "Name"]]] for i in (*mentioned, *entities)],
            [" a prompt"],
        ],
        None,
        [[e] for e in entities] or None,
        None,
    ]
    inner = [None, [entry], 1, [None, 22, None, None, None, project]]
    return "f.req=" + json.dumps([[["ogiZ0b", json.dumps(inner), None, "generic"]]]) + "&at=x&"
