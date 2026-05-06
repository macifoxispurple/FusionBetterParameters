"""
test_export_package.py — tests for _export_parameters_package record shape and field inclusion.

File I/O is directed to tmp_path. Dialog is bypassed by passing an explicit filePath.
_collect_user_parameters is patched to return canned data — no live design needed.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
import BetterParameters as bp


SAMPLE_PARAMS = [
    {
        "name": "width",
        "expression": "100 mm",
        "unit": "mm",
        "comment": "Overall width",
        "group": "Dimensions",
        "isFavorite": True,
        "metadataRevision": 3,
        "metadataChangedAt": 1713350400000,
    },
    {
        "name": "height",
        "expression": "50 mm",
        "unit": "mm",
        "comment": "",
        "group": "Dimensions",
        "isFavorite": False,
        "metadataRevision": 1,
        "metadataChangedAt": 1713000000000,
    },
    {
        "name": "angle",
        "expression": "45 deg",
        "unit": "deg",
        "comment": "Draft angle",
        "group": "Angles",
        "isFavorite": False,
        "metadataRevision": 0,
        "metadataChangedAt": 0,
    },
]


def export_to_tmp(tmp_path, **kwargs):
    """Run _export_parameters_package writing to a temp file. Returns the parsed package."""
    out_path = str(tmp_path / "out.bpmeta.json")
    data = {"filePath": out_path, **kwargs}
    with patch.object(bp, "_collect_user_parameters", return_value=SAMPLE_PARAMS):
        with patch.object(bp, "_design", return_value=None):
            result = bp._export_parameters_package(data)
    assert not result.get("cancelled"), f"Unexpected cancel: {result}"
    assert result["exportedCount"] == len(SAMPLE_PARAMS)
    assert os.path.exists(out_path)
    return json.loads(Path(out_path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Package structure
# ---------------------------------------------------------------------------

class TestExportPackageStructure:
    def test_schema_version_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["schemaVersion"] == bp.BPMETA_SCHEMA_VERSION

    def test_exported_at_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert "exportedAt" in pkg
        assert pkg["exportedAt"] != ""

    def test_source_document_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert "sourceDocument" in pkg
        assert isinstance(pkg["sourceDocument"], dict)

    def test_parameters_array_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert isinstance(pkg["parameters"], list)
        assert len(pkg["parameters"]) == len(SAMPLE_PARAMS)

    def test_parameter_order_preserved(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        names = [r["name"] for r in pkg["parameters"]]
        assert names == [p["name"] for p in SAMPLE_PARAMS]


# ---------------------------------------------------------------------------
# Required fields always present
# ---------------------------------------------------------------------------

class TestExportRequiredFields:
    def test_name_always_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        for record in pkg["parameters"]:
            assert "name" in record

    def test_expression_always_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        for record in pkg["parameters"]:
            assert "expression" in record

    def test_unit_always_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        for record in pkg["parameters"]:
            assert "unit" in record

    def test_metadata_revision_always_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        for record in pkg["parameters"]:
            assert "metadataRevision" in record

    def test_metadata_changed_at_always_present(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        for record in pkg["parameters"]:
            assert "metadataChangedAt" in record


# ---------------------------------------------------------------------------
# Optional fields — default on (include* defaults True)
# ---------------------------------------------------------------------------

class TestExportOptionalFieldsDefaultOn:
    def test_comment_included_by_default(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert all("comment" in r for r in pkg["parameters"])

    def test_group_included_by_default(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert all("group" in r for r in pkg["parameters"])

    def test_is_favorite_included_by_default(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert all("isFavorite" in r for r in pkg["parameters"])

    def test_display_order_absent_by_default(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert all("displayOrder" not in r for r in pkg["parameters"])


# ---------------------------------------------------------------------------
# Optional fields — explicitly disabled
# ---------------------------------------------------------------------------

class TestExportOptionalFieldsDisabled:
    def test_comment_excluded_when_false(self, tmp_path):
        pkg = export_to_tmp(tmp_path, includeComments=False)
        assert all("comment" not in r for r in pkg["parameters"])

    def test_group_excluded_when_false(self, tmp_path):
        pkg = export_to_tmp(tmp_path, includeGroups=False)
        assert all("group" not in r for r in pkg["parameters"])

    def test_is_favorite_excluded_when_false(self, tmp_path):
        pkg = export_to_tmp(tmp_path, includeFavorites=False)
        assert all("isFavorite" not in r for r in pkg["parameters"])

    def test_metadata_revision_present_even_when_all_disabled(self, tmp_path):
        pkg = export_to_tmp(tmp_path, includeComments=False, includeGroups=False, includeFavorites=False)
        assert all("metadataRevision" in r for r in pkg["parameters"])
        assert all("metadataChangedAt" in r for r in pkg["parameters"])


# ---------------------------------------------------------------------------
# displayOrder
# ---------------------------------------------------------------------------

class TestExportDisplayOrder:
    def test_display_order_absent_when_false(self, tmp_path):
        pkg = export_to_tmp(tmp_path, includeOrder=False)
        assert all("displayOrder" not in r for r in pkg["parameters"])

    def test_display_order_present_when_true(self, tmp_path):
        pkg = export_to_tmp(tmp_path, includeOrder=True)
        assert all("displayOrder" in r for r in pkg["parameters"])

    def test_display_order_sequential_from_zero(self, tmp_path):
        pkg = export_to_tmp(tmp_path, includeOrder=True)
        orders = [r["displayOrder"] for r in pkg["parameters"]]
        assert orders == list(range(len(SAMPLE_PARAMS)))


# ---------------------------------------------------------------------------
# Field value correctness
# ---------------------------------------------------------------------------

class TestExportFieldValues:
    def test_name_value_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["name"] == "width"

    def test_expression_value_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["expression"] == "100 mm"

    def test_unit_value_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["unit"] == "mm"

    def test_comment_value_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["comment"] == "Overall width"

    def test_group_value_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["group"] == "Dimensions"

    def test_is_favorite_true_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["isFavorite"] is True

    def test_is_favorite_false_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][1]["isFavorite"] is False

    def test_metadata_revision_value_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["metadataRevision"] == 3

    def test_metadata_changed_at_value_correct(self, tmp_path):
        pkg = export_to_tmp(tmp_path)
        assert pkg["parameters"][0]["metadataChangedAt"] == 1713350400000


# ---------------------------------------------------------------------------
# Cancelled / no-op when filePath empty (dialog not available in test env)
# ---------------------------------------------------------------------------

def test_cancel_when_no_ui_and_no_filepath():
    """With no filePath and no ui, should raise (UI unavailable) or cancel."""
    with patch.object(bp, "_collect_user_parameters", return_value=SAMPLE_PARAMS):
        with patch.object(bp, "_design", return_value=None):
            with patch.object(bp, "ui", None):
                try:
                    result = bp._export_parameters_package({"filePath": ""})
                    assert result.get("cancelled") is True
                except RuntimeError as exc:
                    assert "UI" in str(exc)


# ---------------------------------------------------------------------------
# File extension appended when missing
# ---------------------------------------------------------------------------

def test_extension_appended_when_missing(tmp_path):
    # Pass a path without .bpmeta.json extension
    out_path = str(tmp_path / "out")
    with patch.object(bp, "_collect_user_parameters", return_value=SAMPLE_PARAMS):
        with patch.object(bp, "_design", return_value=None):
            result = bp._export_parameters_package({"filePath": out_path})
    # File should exist with the extension appended
    assert result["filePath"].endswith(".bpmeta.json")
    assert os.path.exists(result["filePath"])
