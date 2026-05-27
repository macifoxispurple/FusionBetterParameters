from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = REPO_ROOT / "BetterParameters" / "palette.html"
MOCK_FIXTURES_PATH = REPO_ROOT / "BetterParameters" / "dev" / "mock_bridge_fixtures.js"
RENDER_DATASET_PATH = REPO_ROOT / "tests" / "fixtures" / "render_test_datasets.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_palette_mock_bridge_mode_wiring_present():
    text = _read(PALETTE_PATH)
    assert "__BP_USE_MOCK_BRIDGE" in text
    assert "dev/mock_bridge_fixtures.js" in text


def test_generated_render_fixture_assets_present():
    assert MOCK_FIXTURES_PATH.exists()
    assert RENDER_DATASET_PATH.exists()
    assert "render-large" in _read(MOCK_FIXTURES_PATH)
    assert '"defaultMode": "render-smoke"' in _read(RENDER_DATASET_PATH)


def test_rapid_create_batch_workspace_markers_present():
    text = _read(PALETTE_PATH)
    assert "rapidCreateValidateBatch" in text
    assert "rapidCreatePreviewBatch" in text
    assert "rapidCreateApplyBatch" in text
    assert "rapidCreateGridBody" in text
    assert "rapidCreateApplyButton" in text


def test_palette_cmd_ctrl_parity_shortcuts_present():
    text = _read(PALETTE_PATH)
    assert "const ctrlOrMeta = event.ctrlKey || event.metaKey;" in text
    assert "const isLayoutDebugToggle = keyLower === \"d\" && (" in text
    assert "const isTextTunerToggle = keyLower === \"t\" && ctrlOrMeta" in text
    assert "const isComputeModeToggleShortcut = keyLower === \"m\" && ctrlOrMeta" in text
    assert "const isRapidCreateShortcut = keyLower === \"c\" && ctrlOrMeta" in text


def test_palette_contains_core_controls_ids():
    text = _read(PALETTE_PATH)
    expected_ids = [
        "computeModeButton",
        "applyAllButton",
        "discardAllButton",
        "importParametersButton",
        "importParametersPackageButton",
        "timelineSortButton",
        "parameterRows",
    ]
    for control_id in expected_ids:
        assert f'id="{control_id}"' in text
