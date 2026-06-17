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


def test_palette_cmd_ctrl_parity_shortcuts_present():
    text = _read(PALETTE_PATH)
    assert "const ctrlOrMeta = event.ctrlKey || event.metaKey;" in text
    assert "const isCreateModalShortcut = keyLower === \"c\" && ctrlOrMeta && event.shiftKey && !event.altKey;" in text
    assert "const isLayoutDebugToggle = keyLower === \"d\" && (" in text
    assert "const isTextTunerToggle = keyLower === \"t\" && ctrlOrMeta" in text
    assert "const isComputeModeToggleShortcut = keyLower === \"m\" && ctrlOrMeta" in text


def test_palette_contains_core_controls_ids():
    text = _read(PALETTE_PATH)
    expected_ids = [
        "computeModeButton",
        "applyAllButton",
        "discardAllButton",
        "importParametersButton",
        "includeMetadataParameterCsvToggle",
        "timelineSortButton",
        "parameterRows",
        "createShortcutTip",
    ]
    for control_id in expected_ids:
        assert f'id="{control_id}"' in text


def test_palette_has_stable_root_component_group_identity():
    text = _read(PALETTE_PATH)
    assert 'const ROOT_COMPONENT_GROUP_LABEL = "Root Component";' in text
    assert 'const ROOT_COMPONENT_ID = "root";' in text
    assert "function isRootComponentModelValue(value)" in text
    assert "value?.isRootComponent === true" in text


def test_palette_import_response_helpers_present():
    text = _read(PALETTE_PATH)
    assert 'function readResponseCountField(response, fieldName, contextLabel = "Response")' in text
    assert 'function readResponseArrayField(response, fieldName, contextLabel = "Response")' in text
