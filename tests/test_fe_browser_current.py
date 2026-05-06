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
    palette = repo_root / "BetterParameters" / "palette.html"
    base = f"file:///{quote(str(palette).replace('\\', '/'), safe='/:')}"
    return f"{base}?mock=1&layoutdebug=1"


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
    page.locator("#computeModeButton").wait_for(timeout=10000)
    page.locator("#parameterRows tr.parameter-row[data-parameter-key]").first.wait_for(timeout=10000)
    return page


def test_palette_loads_directly(browser_page):
    page = browser_page
    page.goto(_harness_url())
    ready_page = _wait_palette_ready(page)
    assert ready_page.locator("#computeModeButton").count() == 1


def test_fe_shortcut_toggle_layout_debug(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)
    body = page.locator("body")
    initial = body.get_attribute("class") or ""
    page.keyboard.press("Control+Alt+D")
    page.wait_for_timeout(120)
    after = body.get_attribute("class") or ""
    assert initial != after


def test_apply_all_and_discard_all_controls_present(browser_page):
    page = browser_page
    page.goto(_harness_url())
    ready_page = _wait_palette_ready(page)
    assert ready_page.locator("#applyAllButton").count() == 1
    assert ready_page.locator("#discardAllButton").count() == 1
    assert ready_page.locator("#timelineSortButton").count() == 1


def test_timeline_sort_disabled_when_row_dirty(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)
    row = page.query_selector("#parameterRows tr.parameter-row[data-parameter-key]")
    assert row is not None
    comment = row.query_selector(".comment-input")
    assert comment is not None
    page.evaluate(
        """(el) => {
            el.value = "timeline-dirty-smoke";
            el.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        comment,
    )
    timeline = page.query_selector("#timelineSortButton")
    assert timeline is not None
    assert timeline.is_disabled()


def test_apply_all_disabled_when_expression_invalid(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)
    row = page.query_selector("#parameterRows tr.parameter-row[data-parameter-key]")
    assert row is not None
    expr = row.query_selector(".expression-input")
    assert expr is not None
    page.evaluate(
        """(el) => {
            el.value = "";
            el.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        expr,
    )
    apply_all = page.query_selector("#applyAllButton")
    assert apply_all is not None
    assert apply_all.is_disabled()


def test_discard_all_clears_dirty_rows(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)
    rows = page.query_selector_all("#parameterRows tr.parameter-row[data-parameter-key]")
    assert len(rows) >= 2
    for idx, row in enumerate(rows[:2]):
        comment = row.query_selector(".comment-input")
        assert comment is not None
        page.evaluate(
            """([el, text]) => {
                el.value = text;
                el.dispatchEvent(new Event("input", { bubbles: true }));
            }""",
            [comment, f"discard-all-{idx}"],
        )
        assert "is-dirty" in (row.get_attribute("class") or "")
    discard_all = page.query_selector("#discardAllButton")
    assert discard_all is not None
    discard_all.click()
    page.wait_for_timeout(150)
    for row in rows[:2]:
        assert "is-dirty" not in (row.get_attribute("class") or "")
