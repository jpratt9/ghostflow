"""human_mouse: a person's click on a Playwright page, and Playwright's own where it can't aim."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api import human_mouse


def _locator(box: object, hit: bool = True) -> tuple[MagicMock, MagicMock]:
    page = MagicMock()
    page.mouse = MagicMock(move=AsyncMock(), down=AsyncMock(), up=AsyncMock())
    page.evaluate = AsyncMock(return_value=[1280, 800])
    locator = MagicMock(page=page)
    locator.bounding_box = AsyncMock(return_value=box)
    locator.evaluate = AsyncMock(return_value=hit)
    locator.click = AsyncMock()
    return locator, page


def test_a_move_ends_exactly_on_its_target_in_20_to_120_steps() -> None:
    for end in ((105.0, 210.0), (1200.0, 40.0)):
        points = human_mouse._path((100.0, 200.0), end)  # pyright: ignore[reportPrivateUsage]
        assert points[-1] == end
        assert 20 <= len(points) <= 120


def test_a_farther_or_smaller_target_takes_longer() -> None:
    fitts = human_mouse._fitts  # pyright: ignore[reportPrivateUsage]
    assert fitts(800, 20) > fitts(100, 20) > fitts(100, 200)


@pytest.mark.asyncio
async def test_a_click_travels_to_a_point_inside_the_element_and_presses_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(human_mouse.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(human_mouse, "_rest", AsyncMock())  # its tremor's timing isn't tested here
    locator, page = _locator({"x": 300, "y": 500, "width": 500, "height": 120})
    await human_mouse.human_click(locator)
    locator.click.assert_not_awaited()
    assert page.mouse.move.await_count >= 20  # a path, not a jump
    x, y = page.mouse.move.await_args_list[-1].args
    assert 302 <= x <= 798 and 502 <= y <= 618  # its last move lands inside, where it presses
    page.mouse.down.assert_awaited_once()
    page.mouse.up.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("box", "hit"),
    [
        (None, True),  # not laid out
        ({"x": -5, "y": 10, "width": 50, "height": 40}, True),  # partly off screen
        ({"x": 10, "y": 10, "width": 50, "height": 40}, False),  # something else on top of it
        (MagicMock(), True),  # won't be measured
    ],
)
async def test_one_it_cant_aim_at_gets_playwrights_own_click(box: object, hit: bool) -> None:
    locator, page = _locator(box, hit)
    await human_mouse.human_click(locator, timeout_ms=4000)
    locator.click.assert_awaited_once_with(timeout=4000)
    page.mouse.down.assert_not_awaited()
