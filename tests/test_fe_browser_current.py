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


def _harness_url(fixture: str = "") -> str:
    repo_root = Path(__file__).resolve().parents[1]
    palette = repo_root / "BetterParameters" / "palette.html"
    base = f"file:///{quote(str(palette).replace('\\', '/'), safe='/:')}"
    suffix = f"&fixture={quote(fixture)}" if fixture else ""
    return f"{base}?mock=1&layoutdebug=1{suffix}"


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
    page.locator("#computeModeButton").wait_for(timeout=10000, state="attached")
    page.locator("#parameterRows tr.parameter-row[data-parameter-key]").first.wait_for(timeout=10000)
    return page


def _open_rapid_create(page):
    page.keyboard.press("Control+Shift+C")
    page.locator("#rapidCreateModal").wait_for(timeout=10000, state="visible")
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
    page.evaluate("() => window.setComputeMode('manual')")
    rows = page.query_selector_all("#parameterRows tr.parameter-row[data-parameter-key]:not([data-favorites-row='true'])")
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
    page.evaluate("() => window.discardAllDirtyRows()")
    page.wait_for_timeout(150)
    for row in rows[:2]:
        assert "is-dirty" not in (row.get_attribute("class") or "")


def test_large_render_fixture_renders_expected_rows_and_groups(browser_page):
    page = browser_page
    page.goto(_harness_url("render-large"))
    _wait_palette_ready(page)
    page.wait_for_timeout(150)

    rows = page.locator("#parameterRows tr.parameter-row[data-parameter-key]")
    groups = page.locator("#parameterRows tr.group-header-row")

    assert rows.count() >= 180
    assert groups.count() >= 6
    assert page.locator("#contractErrorBanner[hidden]").count() == 1
    assert page.locator("#parameterRows").text_content() and "DIMENSIONS_Fixture_001" in page.locator("#parameterRows").text_content()


def test_rapid_create_modal_opens_with_grid_workspace(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)
    _open_rapid_create(page)
    assert page.locator("#rapidCreateGridBody").count() == 1
    assert page.locator("#rapidCreateApplyButton").count() == 1
    assert page.locator("#rapidCreateIssueList").count() == 1


def test_rapid_create_import_validate_preview_and_apply(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)
    _open_rapid_create(page)

    page.locator("#rapidCreatePasteButton").click()
    editor = page.locator("#rapidCreateEditor")
    editor.fill("DIMENSIONS_Fixture_001\tDIMENSIONS_Fixture_001_RENAMED\t42 mm\tmm\tRenamed row\trename\n\tFreshFixtureParam\t25 mm\tmm\tCreated row\tcreate")
    page.locator("#rapidCreateNormalizeButton").click()

    rows = page.locator("#rapidCreateGridBody tr[data-rapid-row-key]")
    assert rows.count() == 2
    assert page.locator("#rapidCreateSummary").text_content()

    page.locator("#rapidCreateValidateButton").click()
    page.wait_for_timeout(150)
    assert "Validation" in (page.locator("#rapidCreateActiveStatus").text_content() or "")

    page.locator("#rapidCreatePreviewButton").click()
    page.wait_for_timeout(150)
    assert "42 mm" in (rows.nth(0).text_content() or "")
    assert "25 mm" in (rows.nth(1).text_content() or "")

    page.locator("#rapidCreateApplyButton").click()
    page.wait_for_timeout(250)
    page.locator("#rapidCreateModal").wait_for(timeout=10000, state="hidden")
    assert page.locator("#rapidCreateModal").is_hidden()


def test_new_parameter_expression_is_single_line_and_enter_submits(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)

    page.locator("#newParamButton").click()
    page.locator("#createModal").wait_for(timeout=10000, state="visible")
    page.locator("#newName").fill("BrowserCreateParam")

    page.evaluate(
        """() => {
            const input = document.getElementById("newExpression");
            input.value = "10 mm\\n20 mm";
            input.dispatchEvent(new Event("input", { bubbles: true }));
        }"""
    )
    page.wait_for_timeout(100)
    assert "\n" not in (page.locator("#newExpression").input_value() or "")

    page.goto(_harness_url())
    _wait_palette_ready(page)

    page.locator("#newParamButton").click()
    page.locator("#createModal").wait_for(timeout=10000, state="visible")
    assert (page.locator("#createSubmitButton").text_content() or "").strip() == "Done"
    page.locator("#newName").fill("BrowserCreateParam")
    page.locator("#newExpression").fill("10 mm")
    assert (page.locator("#createSubmitButton").text_content() or "").strip() == "Add and Create New"
    page.locator("#newExpression").press("Shift+Enter")
    page.wait_for_timeout(200)
    assert page.locator("#createModal").is_visible()
    assert (page.locator("#newName").input_value() or "") == ""
    assert (page.locator("#newExpression").input_value() or "") == ""
    assert (page.locator("#newComment").input_value() or "") == ""
    focused_id = page.evaluate("() => document.activeElement && document.activeElement.id")
    assert focused_id == "newName"
    assert (page.locator("#createSubmitButton").text_content() or "").strip() == "Done"

    page.locator("#newName").fill("BrowserCreateParamTwo")
    page.locator("#newExpression").fill("12 mm")
    page.locator("#newExpression").press("Enter")
    page.wait_for_timeout(200)
    assert page.locator("#createModal").is_visible()
    assert (page.locator("#newName").input_value() or "") == ""
    assert (page.locator("#newExpression").input_value() or "") == ""
    assert (page.locator("#createSubmitButton").text_content() or "").strip() == "Done"

    page.locator("#newName").press("Enter")
    page.locator("#createModal").wait_for(timeout=10000, state="hidden")
