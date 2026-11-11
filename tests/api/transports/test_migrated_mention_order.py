"""#997: every ``@`` mention lands AFTER the chips already in the prompt, or the run stops.

Measured (docs/superpowers/spikes/2026-10-19-fourth-ref-caret.md, denon82, 3/3): with three
chips on the line, a click on the composer's centre lands on chip 2 and leaves the caret
behind it, so reference 4 was inserted between chips 2 and 3 — order ``1, 2, 4, 3`` — and
the count-only guards passed it. The fake below models exactly that wedge: a click puts
the caret behind chip 2 once three chips are present, Enter inserts at the caret, and only
a caret moved to the END of the composer (a collapsed DOM Range) puts it back.
"""

from __future__ import annotations

from typing import Any

import pytest

from gflow_cli.errors import ReferenceNotFoundError

pytestmark = pytest.mark.anyio


class _Loc:
    def __init__(self, page: _CaretPage, kind: str) -> None:
        self.page, self.kind = page, kind

    @property
    def first(self) -> _Loc:
        return self

    async def click(self, **_: Any) -> None:
        if self.kind == "composer":
            # The measured wedge: the centre of a line holding 3 chips is chip 2.
            n = len(self.page.chips)
            self.page.caret = 2 if n >= 3 else n

    async def all_text_contents(self) -> list[str]:
        return [self.page.query]


class _Keyboard:
    def __init__(self, page: _CaretPage) -> None:
        self.page = page

    async def type(self, text: str, **_: Any) -> None:
        if text not in ("@", " "):
            self.page.query = text

    async def press(self, key: str) -> None:
        if key == "Enter":
            chip = {"text": self.page.query, "entity_id": "", "reference_type": self.page.kind}
            self.page.chips.insert(self.page.caret, chip)
            self.page.caret += 1


class _CaretPage:
    def __init__(self, kind: str, *, caret_js_works: bool = True) -> None:
        self.kind = kind
        self.caret_js_works = caret_js_works
        self.chips: list[dict[str, str]] = []
        self.caret = 0
        self.query = ""
        self.keyboard = _Keyboard(self)

    def locator(self, css: str) -> _Loc:
        return _Loc(self, "composer" if "contenteditable" in css else "option")

    async def wait_for_timeout(self, _ms: float) -> None:
        return None

    async def evaluate(self, script: str, _arg: Any = None) -> Any:
        if "collapse(false)" in script:
            if self.caret_js_works:
                self.caret = len(self.chips)
            return None
        if "asset-title" in script:
            return [self.query]
        if "asb" in script:
            return [f"tok-{self.query}"]
        return [dict(c) for c in self.chips]


NAMES = ("one", "two", "three", "four", "five")


async def _mention(page: _CaretPage, kind: str, name: str, n: int) -> None:
    from gflow_cli.api.transports.migrated_composer import MigratedComposer

    composer = MigratedComposer()
    if kind == "media-token":
        await composer._mention_by_token(page, name, f"tok-{name}", name, expect_chips=n)  # noqa: SLF001
    elif kind == "media-name":
        await composer._mention_by_name(page, name, expect_chips=n)  # noqa: SLF001
    else:
        await composer._mention_character(page, name, expect_chips=n)  # noqa: SLF001


KINDS = [("media-token", "media"), ("media-name", "media"), ("character", "entity")]


@pytest.mark.parametrize(("path", "chip_kind"), KINDS)
async def test_five_mentions_land_in_the_order_requested(path: str, chip_kind: str) -> None:
    page = _CaretPage(chip_kind)
    for n, name in enumerate(NAMES, start=1):
        await _mention(page, path, name, n)
    assert [c["text"] for c in page.chips] == list(NAMES)


@pytest.mark.parametrize(("path", "chip_kind"), KINDS)
async def test_a_mention_that_lands_mid_prompt_is_refused(path: str, chip_kind: str) -> None:
    """Whatever puts the caret in the wrong place next, a misordered prompt never ships
    silently: the chips already there must stay a prefix of the chips after."""
    page = _CaretPage(chip_kind, caret_js_works=False)
    for n, name in enumerate(NAMES[:3], start=1):
        await _mention(page, path, name, n)
    with pytest.raises(ReferenceNotFoundError, match="out of order") as caught:
        await _mention(page, path, NAMES[3], 4)
    # The chip WAS found; the class default ("not in this project's picker") would mislead.
    assert "not in this project" not in caught.value.remediation_hint
    assert "order" in caught.value.remediation_hint
