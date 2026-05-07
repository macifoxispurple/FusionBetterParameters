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
