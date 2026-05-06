from pathlib import Path
from urllib.parse import quote

import pytest


pytestmark = pytest.mark.fe_browser


def _playwright_import():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return None
    return sync_playwright


def _harness_url() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    harness = repo_root / "devtools" / "dev_harness.html"
    return f"file:///{quote(str(harness).replace('\\', '/'), safe='/:')}"


@pytest.fixture(scope="module")
def browser_page():
    sync_playwright = _playwright_import()
    if sync_playwright is None:
        pytest.skip("Playwright not installed. Install with: python -m pip install playwright && python -m playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            yield page
        finally:
            browser.close()


def _wait_palette_ready(page):
    page.wait_for_selector("#paletteFrame", timeout=10000)
    frame = page.frame_locator("#paletteFrame")
    frame.locator("#computeModeButton").wait_for(timeout=10000)
    frame.locator("#parameterRows tr.parameter-row[data-parameter-key]").first.wait_for(timeout=10000)
    return frame


def test_dev_harness_loads_palette(browser_page):
    page = browser_page
    page.goto(_harness_url())
    frame = _wait_palette_ready(page)
    assert frame.locator("#computeModeButton").count() == 1


def test_fe_shortcut_toggle_layout_debug(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)
    frame = page.frame_locator("#paletteFrame")
    body = frame.locator("body")
    initial = body.get_attribute("class") or ""
    page.keyboard.press("Control+Alt+D")
    page.wait_for_timeout(120)
    after = body.get_attribute("class") or ""
    assert initial != after


def test_apply_all_and_discard_all_controls_present(browser_page):
    page = browser_page
    page.goto(_harness_url())
    frame = _wait_palette_ready(page)
    assert frame.locator("#applyAllButton").count() == 1
    assert frame.locator("#discardAllButton").count() == 1
    assert frame.locator("#timelineSortButton").count() == 1

