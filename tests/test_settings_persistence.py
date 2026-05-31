from pathlib import Path

import pytest

import BetterParameters as BP


def test_load_settings_without_file_uses_first_run_left_docked_width(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    loaded = BP._load_settings()

    assert loaded["paletteDockingState"] == "left"
    assert loaded["paletteSize"]["width"] == BP.FIRST_RUN_PALETTE_WIDTH
    assert loaded["palettePosition"] == {}


def test_load_settings_existing_file_without_geometry_keeps_general_palette_defaults(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)
    settings_path.write_text("{}", encoding="utf-8")

    loaded = BP._load_settings()

    assert loaded["paletteDockingState"] == BP.DEFAULT_SETTINGS["paletteDockingState"]
    assert loaded["paletteSize"]["width"] == BP.DEFAULT_SETTINGS["paletteSize"]["width"]


def test_initial_palette_settings_file_is_written_left_docked_without_height(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    wrote = BP._ensure_initial_palette_settings_file()

    assert wrote is True
    raw = settings_path.read_text(encoding="utf-8")
    assert '"paletteDockingState": "left"' in raw
    assert '"width": 324' in raw
    assert '"height"' not in raw
    assert '"autoOpenOnStart": true' in raw


def test_apply_saved_palette_size_preserves_fusion_height_when_settings_height_absent(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)
    settings_path.write_text('{"paletteSize":{"width":324},"paletteDockingState":"left"}', encoding="utf-8")

    class Palette:
        width = 999
        height = 777

    palette = Palette()
    BP._apply_saved_palette_size(palette)

    assert palette.width == 324
    assert palette.height == 777


def test_first_run_pending_ignores_default_floating_geometry_save(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)
    BP._ensure_initial_palette_settings_file()

    saved = BP._save_palette_geometry_settings({
        "paletteSize": {"width": 760, "height": 640},
        "palettePosition": {"x": 0, "y": 0},
        "paletteDockingState": "floating",
    })

    assert saved["paletteDockingState"] == "left"
    assert saved["paletteSize"]["width"] == 324
    assert saved["palettePosition"] == {}
    assert saved["paletteInitialDockingPending"] is True


def test_first_run_pending_clears_after_docked_size_save(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)
    BP._ensure_initial_palette_settings_file()

    saved = BP._save_palette_geometry_settings({
        "paletteSize": {"width": 324, "height": 866},
    })

    assert saved["paletteDockingState"] == "left"
    assert saved["paletteSize"] == {"width": 324, "height": 866}
    assert saved["paletteInitialDockingPending"] is False


def test_save_settings_persists_ultralight_narrow_ui(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    saved = BP._save_settings({"ultralightNarrowUi": True})

    assert saved["ultralightNarrowUi"] is True
    loaded = BP._load_settings()
    assert loaded["ultralightNarrowUi"] is True


def test_save_settings_rejects_non_boolean_ultralight_narrow_ui(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    with pytest.raises(ValueError, match='"ultralightNarrowUi" must be a boolean.'):
        BP._save_settings({"ultralightNarrowUi": "yes"})


def test_save_settings_persists_parameter_table_column_order(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    order = ["name", "parameter", "value", "comment", "revert", "unit", "expression"]
    saved = BP._save_settings({"parameterTableColumnOrder": order})

    assert saved["parameterTableColumnOrder"] == order
    loaded = BP._load_settings()
    assert loaded["parameterTableColumnOrder"] == order


def test_save_settings_rejects_non_array_parameter_table_column_order(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    with pytest.raises(ValueError, match='"parameterTableColumnOrder" must be an array.'):
        BP._save_settings({"parameterTableColumnOrder": "name,parameter"})


def test_load_settings_sanitizes_parameter_table_column_order(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)
    settings_path.write_text(
        '{"parameterTableColumnOrder":["name","name","unknown","value"]}',
        encoding="utf-8",
    )

    loaded = BP._load_settings()
    assert loaded["parameterTableColumnOrder"] == [
        "name",
        "value",
        "parameter",
        "unit",
        "expression",
        "comment",
        "revert",
    ]


def test_save_settings_persists_hide_groups(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    saved = BP._save_settings({"hideGroups": True})

    assert saved["hideGroups"] is True
    loaded = BP._load_settings()
    assert loaded["hideGroups"] is True


def test_save_settings_rejects_non_boolean_hide_groups(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    with pytest.raises(ValueError, match='"hideGroups" must be a boolean.'):
        BP._save_settings({"hideGroups": "yes"})


def test_reset_settings_to_defaults_deletes_customized_settings_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    BP._save_settings({"theme": "light", "hideGroups": True})
    assert settings_path.exists()

    reset = BP._reset_settings_to_defaults()
    assert reset["theme"] == BP.DEFAULT_SETTINGS["theme"]
    assert reset["hideGroups"] == BP.DEFAULT_SETTINGS["hideGroups"]
    assert not settings_path.exists()


def test_reset_settings_to_defaults_when_file_missing_returns_defaults(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(BP, "_settings_path", lambda: settings_path)

    reset = BP._reset_settings_to_defaults()
    assert reset["theme"] == BP.DEFAULT_SETTINGS["theme"]
    assert reset["hideGroups"] == BP.DEFAULT_SETTINGS["hideGroups"]
