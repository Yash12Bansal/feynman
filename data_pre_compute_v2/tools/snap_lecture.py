"""Headless screenshot tool for the lecture-preview React route.

Drives Chromium against http://localhost:5173/#/lecture-preview?chapter=...
so we can iterate on the UI without manual screenshotting.

Usage:
    poetry run python tools/snap_lecture.py
    poetry run python tools/snap_lecture.py --play-seconds 8 --output /tmp/foo.png
    poetry run python tools/snap_lecture.py --play-seconds 0   # no autoplay
    poetry run python tools/snap_lecture.py --console-log      # also dump console errors

Both servers must be running:
    Terminal A:  cd data_pre_compute_v2 && poetry run python tools/preview_server.py
    Terminal B:  cd frontend && pnpm dev
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

DEFAULT_CHAPTER = "chapter:physics:newtons_laws_of_motion"
DEFAULT_URL_TEMPLATE = "http://localhost:5173/#/lecture-preview?chapter={chapter}"


async def snap(
    chapter_id: str,
    output: Path,
    play_seconds: float,
    *,
    width: int,
    height: int,
    console_log: bool,
    base_url: str,
) -> None:
    url = base_url.format(chapter=chapter_id)
    print(f"  → {url}")
    output.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": width, "height": height})
        page = await context.new_page()

        console_msgs: list[str] = []
        if console_log:
            page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda exc: console_msgs.append(f"[pageerror] {exc}"))

        await page.goto(url, wait_until="networkidle")
        # Player isn't auto-mounted unless ?chapter= is present, so the page
        # always has #player or #chapter-list visible by now. Give React one
        # more tick in case state hydration is async.
        await asyncio.sleep(0.5)

        if play_seconds > 0:
            # Click the play button if present.
            play_btn = page.locator("#play-btn, button:has-text('Play'), button:has-text('▶')").first
            try:
                await play_btn.click(timeout=2_000)
                await asyncio.sleep(play_seconds)
            except Exception as e:
                print(f"  (play button click skipped: {e})")

        await page.screenshot(path=str(output), full_page=False)
        print(f"  saved → {output} ({output.stat().st_size // 1024} KB)")

        if console_log:
            errors_path = output.with_suffix(".console.txt")
            errors_path.write_text("\n".join(console_msgs) or "(no console output)")
            errs = [m for m in console_msgs if "[error]" in m or "[pageerror]" in m]
            print(f"  console: {len(console_msgs)} messages, {len(errs)} errors → {errors_path}")

        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", default=DEFAULT_CHAPTER)
    parser.add_argument("--output", type=Path, default=Path("/tmp/lecture_snap.png"))
    parser.add_argument("--play-seconds", type=float, default=3.0)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--console-log", action="store_true")
    parser.add_argument(
        "--url-template",
        default=DEFAULT_URL_TEMPLATE,
        help="URL template with {chapter} placeholder.",
    )
    args = parser.parse_args()
    asyncio.run(snap(
        chapter_id=args.chapter,
        output=args.output,
        play_seconds=args.play_seconds,
        width=args.width,
        height=args.height,
        console_log=args.console_log,
        base_url=args.url_template,
    ))


if __name__ == "__main__":
    main()
