"""A person's mouse on a Playwright page: the clicks on Flow's fields before typing, and its submit.

Playwright's own click jumps the pointer to the element's exact centre and presses and releases in
the same instant. This click is modelled on the human mouse in musescore-harvester's captcha solver:
- the pointer travels a curved path to a random point inside the element, drawn about its middle:
  a cubic Bezier bowed to one side, eased by a minimum-jerk profile and timed by Fitts' law;
- on a long move it overshoots a little and comes back;
- it shakes slightly at the ends of a move;
- it rests on the target with a small, smooth tremor for a reaction time, then presses, holds and
  releases.
CDP keeps no pointer position Playwright can read, so each page's is kept here.

An element that isn't laid out on screen, or that something covers where it's aimed at, gets
Playwright's own click, which waits for it, scrolls to it and checks it.
"""

# ruff: noqa: S311 - pointer jitter and timing, not cryptography

from __future__ import annotations

import asyncio
import math
import random
from typing import Any

Point = tuple[float, float]

_POINTER: dict[int, Point] = {}  # each page's pointer, by id(page)
_HIT = (
    "(el, [x, y]) => { const t = document.elementFromPoint(x, y);"
    " return !!t && (el === t || el.contains(t)); }"
)


def _fitts(distance: float, width: float) -> float:
    """Seconds a move of `distance` px onto a target `width` px across takes (Fitts' law)."""
    return 0.05 + 0.10 * math.log2(max(1.0, distance) / max(1.0, width) + 1)


def _min_jerk(t: float) -> float:
    return t * t * t * (10 - 15 * t + 6 * t * t)


def _bezier(p0: float, p1: float, p2: float, p3: float, s: float) -> float:
    return (1 - s) ** 3 * p0 + 3 * (1 - s) ** 2 * s * p1 + 3 * (1 - s) * s * s * p2 + s**3 * p3


def _path(start: Point, end: Point) -> list[Point]:
    """The points of one curved move from `start` to `end`, the last exactly `end`."""
    (x0, y0), (x3, y3) = start, end
    dx, dy = x3 - x0, y3 - y0
    dist = math.hypot(dx, dy) or 1.0
    px, py = -dy / dist, dx / dist  # perpendicular to the move, to bow it to one side
    bow = random.uniform(0.08, 0.22) * dist * random.choice((-1, 1))
    jitter = random.uniform(8, 25)

    def control(lo: float, hi: float, bend: float) -> Point:
        return (
            x0 + dx * random.uniform(lo, hi) + px * bow * bend + random.uniform(-jitter, jitter),
            y0 + dy * random.uniform(lo, hi) + py * bow * bend + random.uniform(-jitter, jitter),
        )

    (x1, y1), (x2, y2) = control(0.10, 0.25, 1.0), control(0.55, 0.75, 0.5)
    steps = max(20, min(120, int(dist / 6)))
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        s = _min_jerk(t)
        shake = max(0.0, 1 - 16 * t * t * (1 - t) * (1 - t))  # none mid-flight, ~1 px at the ends
        points.append(
            (
                _bezier(x0, x1, x2, x3, s) + random.gauss(0, shake),
                _bezier(y0, y1, y2, y3, s) + random.gauss(0, shake),
            )
        )
    points[-1] = end
    return points


async def _walk(page: Any, points: list[Point], seconds: float) -> None:
    pause = seconds / len(points)
    for x, y in points:
        await page.mouse.move(x, y)
        await asyncio.sleep(max(0.005, pause + random.uniform(-0.002, 0.002)))
    _POINTER[id(page)] = points[-1]


async def _travel(page: Any, start: Point, end: Point, width: float) -> None:
    """A move from `start` onto `end`, a target `width` px across: on a long one, 70% of the
    time, a little past it and back, in the time Fitts' law gives the whole."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if math.hypot(dx, dy) > 50 and random.random() < 0.7:
        past = (end[0] + dx * random.uniform(0.03, 0.12), end[1] + dy * random.uniform(0.03, 0.12))
        seconds = _fitts(math.hypot(past[0] - start[0], past[1] - start[1]), width)
        await _walk(page, _path(start, past), 0.85 * seconds)
        await _walk(page, _path(past, end), 0.15 * seconds)
    else:
        await _walk(page, _path(start, end), _fitts(math.hypot(dx, dy), width))


async def _rest(page: Any, at: Point, seconds: float) -> None:
    """The hand resting on `at` for `seconds`: a small, smooth tremor (an Ornstein-Uhlenbeck
    wobble of about 1 px), then still on it."""
    off_x = off_y = 0.0
    loop = asyncio.get_running_loop()
    until = loop.time() + seconds
    while loop.time() < until:
        off_x += -8 * off_x * 0.014 + math.sqrt(2 * 8 * 0.014) * random.gauss(0, 1)
        off_y += -8 * off_y * 0.014 + math.sqrt(2 * 8 * 0.014) * random.gauss(0, 1)
        await page.mouse.move(at[0] + off_x, at[1] + off_y)
        await asyncio.sleep(0.014 + random.uniform(0, 0.006))
    await page.mouse.move(*at)


def _lognormal(median: float, sigma: float, low: float, high: float) -> float:
    return min(high, max(low, random.lognormvariate(math.log(median), sigma)))


def _aim(start: float, span: float) -> float:
    """A point across [start, start + span], drawn about its middle (sigma a quarter of it),
    2 px inside its edges."""
    middle = random.gauss(start + span / 2, max(1.0, span / 4))
    return min(start + span - 2, max(start + 2, middle))


async def _target(locator: Any) -> tuple[Point, float, list[float]] | None:
    """Where to click `locator`, how wide it is and the viewport's size; None when it isn't laid
    out on screen, something else is under the point aimed at, or it won't be measured at all."""
    try:
        box = await locator.bounding_box()
        if not isinstance(box, dict) or box["width"] <= 4 or box["height"] <= 4:
            return None
        view = await locator.page.evaluate("() => [innerWidth, innerHeight]")
        if not (
            box["x"] >= 0
            and box["y"] >= 0
            and box["x"] + box["width"] <= view[0]
            and box["y"] + box["height"] <= view[1]
        ):
            return None
        target = (_aim(box["x"], box["width"]), _aim(box["y"], box["height"]))
        if not await locator.evaluate(_HIT, list(target)):
            return None
        return target, min(box["width"], box["height"]), view
    except Exception:  # noqa: BLE001 - Playwright's own click then says what's wrong with it
        return None


async def human_click(locator: Any, *, timeout_ms: float | None = None) -> None:
    """`locator` clicked as a person clicks it (the module's docstring says how); Playwright's own
    click when it isn't on screen to aim at, or something else is under the point aimed at."""
    aimed = await _target(locator)
    if aimed is None:
        await locator.click(**({"timeout": timeout_ms} if timeout_ms else {}))
        return
    target, width, view = aimed
    page = locator.page
    start = _POINTER.get(id(page)) or (
        random.uniform(0.2, 0.8) * view[0],
        random.uniform(0.3, 0.9) * view[1],
    )
    await _travel(page, start, target, width)
    if random.random() < 0.6:
        await _rest(page, target, random.uniform(0.15, 0.5))  # looking it over
    await _rest(page, target, _lognormal(0.20, 0.30, 0.08, 0.6))  # the reaction before the press
    await asyncio.sleep(random.uniform(0.02, 0.05))
    await page.mouse.down()
    await asyncio.sleep(_lognormal(0.09, 0.30, 0.04, 0.3))
    await page.mouse.up()
