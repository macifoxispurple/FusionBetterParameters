from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = REPO_ROOT / "BetterParameters" / "palette.html"
HARNESS_PATH = REPO_ROOT / "devtools" / "dev_harness.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dev_harness_targets_current_palette_path():
    text = _read(HARNESS_PATH)
    assert "../BetterParameters/palette.html?" in text


def test_palette_mock_fixture_loader_prefers_devtools_path():
    text = _read(PALETTE_PATH)
    assert "../devtools/dev/mock_bridge_fixtures.js" in text
    assert "dev/mock_bridge_fixtures.js" in text


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

