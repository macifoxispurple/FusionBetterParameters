from pathlib import Path

import pytest

import BetterParameters as BP


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
