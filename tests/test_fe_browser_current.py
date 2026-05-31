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


def test_create_modal_shortcut_toggle_and_tip(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)

    page.keyboard.press("Control+Shift+C")
    page.locator("#createModal").wait_for(timeout=10000, state="visible")

    tip_text = (page.locator("#createShortcutTip").text_content() or "").strip()
    assert "Press" in tip_text
    assert "Shift+C" in tip_text
    assert (page.locator("#createSubmitButton").text_content() or "").strip() == "Done"

    footer = page.locator(".create-form-actions")
    assert footer.locator("#createShortcutTip").count() == 1
    assert footer.locator("#createSubmitButton").count() == 1

    page.keyboard.press("Control+Shift+C")
    page.locator("#createModal").wait_for(timeout=10000, state="hidden")


def test_apply_all_and_discard_all_controls_present(browser_page):
    page = browser_page
    page.goto(_harness_url())
    ready_page = _wait_palette_ready(page)
    assert ready_page.locator("#applyAllButton").count() == 1
    assert ready_page.locator("#discardAllButton").count() == 1
    assert ready_page.locator("#timelineSortButton").count() == 1


def test_tiny_width_header_controls_remain_visible(browser_page):
    page = browser_page
    page.set_viewport_size({"width": 340, "height": 820})
    page.goto(_harness_url("render-large"))
    _wait_palette_ready(page)

    for selector in ("#updatePill", "#copySelectedButton", "#deleteSelectedButton", "#timelineSortButton"):
        assert page.locator(selector).is_visible()

    page.locator("#parameterRows tr.parameter-row[data-parameter-key]").first.click()
    chip = page.locator("#selectionCountChip")
    assert chip.is_visible()
    assert (chip.text_content() or "").strip() == "1"

    page.set_viewport_size({"width": 796, "height": 820})


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


def test_refresh_force_applies_backend_state_over_local_draft(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)

    row = page.locator("#parameterRows tr.parameter-row[data-parameter-key]").first
    original_key = row.get_attribute("data-parameter-key") or ""
    assert original_key

    expression = row.locator(".expression-input")
    expression.fill("local unsaved draft")
    assert "is-dirty" in (row.get_attribute("class") or "")

    page.evaluate(
        """([key]) => {
            const nextState = window.buildMockStatePayload();
            nextState.parameters = nextState.parameters.map((param) => {
              if (String(param.key || "") !== key) {
                return param;
              }
              return {
                ...param,
                name: "NativeRefreshName",
                expression: "42 mm",
                valuePreview: "42.00 mm"
              };
            });
            nextState.parameterNames = nextState.parameters.map((param) => param.name);
            window.adsk = {
              fusionSendData: async (action) => {
                if (action === "refresh") {
                  return { ok: true, message: "", state: nextState };
                }
                return { ok: true, message: "", state: null };
              }
            };
        }""",
        [original_key],
    )

    page.evaluate("() => window.refreshParameters({ silentStatus: true })")
    page.wait_for_timeout(250)

    refreshed = page.locator("#parameterRows tr.parameter-row[data-parameter-key]").first
    assert refreshed.locator(".param-name-input").input_value() == "NativeRefreshName"
    assert refreshed.locator(".expression-input").input_value() == "42 mm"
    assert "is-dirty" not in (refreshed.get_attribute("class") or "")


def test_render_state_push_reflects_native_fusion_parameter_change(browser_page):
    page = browser_page
    page.goto(_harness_url())
    _wait_palette_ready(page)

    original_key = page.locator("#parameterRows tr.parameter-row[data-parameter-key]").first.get_attribute("data-parameter-key") or ""
    assert original_key

    page.evaluate(
        """([key]) => {
            const nextState = window.buildMockStatePayload();
            nextState.parameters = nextState.parameters.map((param) => {
              if (String(param.key || "") !== key) {
                return param;
              }
              return {
                ...param,
                name: "NativePushName",
                expression: "24 mm",
                valuePreview: "24.00 mm"
              };
            });
            nextState.parameterNames = nextState.parameters.map((param) => param.name);
            window.fusionReceiveData("renderState", JSON.stringify({ ok: true, message: "", state: nextState }));
        }""",
        [original_key],
    )
    page.wait_for_timeout(150)

    refreshed = page.locator("#parameterRows tr.parameter-row[data-parameter-key]").first
    assert refreshed.locator(".param-name-input").input_value() == "NativePushName"
    assert refreshed.locator(".expression-input").input_value() == "24 mm"


def _selectable_user_rows(page):
    return page.locator("#parameterRows tr.parameter-row[data-parameter-key][data-row-selectable='true']:not([data-favorites-row='true'])")


def _selected_user_row_count(page):
    return page.locator("#parameterRows tr.parameter-row.is-selected[data-row-selectable='true']:not([data-favorites-row='true'])").count()


def _click_row_selector(row, modifiers=None, force_row=False):
    if force_row:
        row.click(position={"x": 12, "y": 12}, modifiers=modifiers or [], force=True)
        return
    row.locator(".parameter-kind").click(modifiers=modifiers or [])


def test_modifier_click_multi_selects_rows(browser_page):
    page = browser_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(_harness_url())
    _wait_palette_ready(page)

    rows = _selectable_user_rows(page)
    assert rows.count() >= 3

    _click_row_selector(rows.nth(0))
    assert _selected_user_row_count(page) == 1

    _click_row_selector(rows.nth(1), modifiers=["Meta"])
    assert _selected_user_row_count(page) == 2
    assert page.locator("#selectionCountChip").text_content() == "2 selected"


def test_shift_click_range_selects_rows_in_narrow_view(browser_page):
    page = browser_page
    page.set_viewport_size({"width": 430, "height": 900})
    page.goto(_harness_url())
    _wait_palette_ready(page)

    rows = _selectable_user_rows(page)
    assert rows.count() >= 5

    _click_row_selector(rows.nth(0), force_row=True)
    _click_row_selector(rows.nth(3), modifiers=["Shift"], force_row=True)
    assert _selected_user_row_count(page) == 4
    assert page.locator("#selectionCountChip").text_content() == "4 selected"


def test_large_render_fixture_renders_expected_rows_and_groups(browser_page):
    page = browser_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(_harness_url("render-large"))
    _wait_palette_ready(page)
    page.wait_for_timeout(150)

    rows = page.locator("#parameterRows tr.parameter-row[data-parameter-key]")
    groups = page.locator("#parameterRows tr.group-header-row")

    assert rows.count() >= 180
    assert groups.count() >= 6
    assert page.locator("#contractErrorBanner[hidden]").count() == 1
    assert page.locator("#parameterRows").text_content() and "DIMENSIONS_Fixture_001" in page.locator("#parameterRows").text_content()


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
    assert (page.locator("#nameError").text_content() or "").strip() == ""
    assert (page.locator("#expressionError").text_content() or "").strip() == ""

    page.locator("#newName").fill("BrowserCreateMissingExpr")
    page.locator("#createSubmitButton").click()
    page.wait_for_timeout(200)
    assert page.locator("#createModal").is_visible()
    assert (page.locator("#expressionError").text_content() or "").strip() == "Expression is required."

    page.locator("#newName").fill("")
    page.wait_for_timeout(100)
    assert (page.locator("#nameError").text_content() or "").strip() == ""
    assert (page.locator("#expressionError").text_content() or "").strip() == ""

    page.locator("#newName").fill("BrowserCreateParamTwo")
    page.locator("#newExpression").fill("12 mm")
    page.locator("#newExpression").press("Enter")
    page.wait_for_timeout(200)
    assert page.locator("#createModal").is_visible()
    assert (page.locator("#newName").input_value() or "") == ""
    assert (page.locator("#newExpression").input_value() or "") == ""
    assert (page.locator("#createSubmitButton").text_content() or "").strip() == "Done"
    assert (page.locator("#nameError").text_content() or "").strip() == ""
    assert (page.locator("#expressionError").text_content() or "").strip() == ""

    page.locator("#newName").press("Enter")
    page.locator("#createModal").wait_for(timeout=10000, state="hidden")
