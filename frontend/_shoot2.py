"""Capture FOCUS spotlight frames on fluid mechanics (post-realign).
Screenshots the first few distinct focus moments so we can SEE the bold glow
+ dim-others on the real board."""

import asyncio

from playwright.async_api import async_playwright

CHAPTER = "chapter:physics:fluid_mechanics"
URL = f"http://localhost:5173/?lecture={CHAPTER}"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(
            headless=True, args=["--autoplay-policy=no-user-gesture-required"]
        )
        ctx = await b.new_context(viewport={"width": 1600, "height": 900})
        await ctx.grant_permissions(["microphone"])
        page = await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded")

        shots = 0
        seen_focus_keys: set[str] = set()
        for _sec in range(150):
            info = await page.evaluate(
                """() => {
                    const f = document.querySelector('.dd-focused');
                    const root = document.querySelector('.dd-has-focus');
                    return {
                        hasFocus: !!f,
                        hasRoot: !!root,
                        focusId: f ? f.getAttribute('data-design-element') : null,
                        title: (document.querySelector('.sb-slide-title')?.textContent||'').slice(0,40),
                        dimmed: document.querySelectorAll('.dd-has-focus [data-design-element]:not(.dd-focused)').length,
                    };
                }"""
            )
            if info["hasFocus"] and info["focusId"]:
                key = f"{info['title']}::{info['focusId']}"
                if key not in seen_focus_keys:
                    seen_focus_keys.add(key)
                    shots += 1
                    path = f"/tmp/fm_focus_{shots:02d}.png"
                    await page.screenshot(path=path)
                    print(
                        f"  shot {shots}: focus='{info['focusId']}' dimmed={info['dimmed']} "
                        f"diagram='{info['title']}' -> {path}",
                        flush=True,
                    )
            if shots >= 5:
                break
            await asyncio.sleep(1)
        print(f"DONE: {shots} focus frames captured", flush=True)
        await b.close()


asyncio.run(main())
