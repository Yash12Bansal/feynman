"""Take a sequence of screenshots through a lecture playback so we can
visually verify the notebook fills up + slide cross-fades as audio plays.

Usage:
    poetry run python tools/snap_lecture_sequence.py
    poetry run python tools/snap_lecture_sequence.py --timestamps 0,5,15,30,60,120
    poetry run python tools/snap_lecture_sequence.py --chapter <chapter_id>
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

DEFAULT_CHAPTER = "chapter:physics:newtons_laws_of_motion"
DEFAULT_URL = (
    "http://localhost:5173/#/lecture-preview?chapter={chapter}"
)
DEFAULT_TIMESTAMPS = "0.5,5,15,30,60,120"


async def snap_sequence(
    chapter_id: str,
    timestamps: list[float],
    output_dir: Path,
    width: int,
    height: int,
    base_url: str,
) -> None:
    url = base_url.format(chapter=chapter_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  → {url}")
    print(f"  timestamps: {timestamps}")
    print(f"  output_dir: {output_dir}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": width, "height": height})
        page = await context.new_page()
        console_msgs: list[str] = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: console_msgs.append(f"[pageerror] {exc}"))

        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(0.4)

        # Click play
        play_btn = page.locator("button:has-text('Play'), button:has-text('▶')").first
        await play_btn.click(timeout=3_000)

        previous = 0.0
        for ts in timestamps:
            await asyncio.sleep(max(0, ts - previous))
            previous = ts
            out_path = output_dir / f"t{ts:06.1f}s.png"
            await page.screenshot(path=str(out_path), full_page=False)
            print(f"    t={ts:6.1f}s → {out_path.name}")

        # Dump console
        log_path = output_dir / "console.txt"
        log_path.write_text("\n".join(console_msgs) or "(no output)")
        errs = [m for m in console_msgs if "[error]" in m or "[pageerror]" in m]
        print(f"  console: {len(console_msgs)} messages, {len(errs)} errors")

        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapter", default=DEFAULT_CHAPTER)
    parser.add_argument("--timestamps", default=DEFAULT_TIMESTAMPS,
                        help="Comma-separated wall-clock seconds (since play click) to snap at.")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/lecture_sequence"))
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--url-template", default=DEFAULT_URL)
    args = parser.parse_args()

    timestamps = sorted(float(t) for t in args.timestamps.split(","))
    asyncio.run(snap_sequence(
        chapter_id=args.chapter,
        timestamps=timestamps,
        output_dir=args.output_dir,
        width=args.width,
        height=args.height,
        base_url=args.url_template,
    ))


if __name__ == "__main__":
    main()
