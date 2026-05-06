"""
test_validate_package_import.py — tests for _validate_parameters_package_import.

All tests pass an explicit filePath (written to tmp_path) so no OS dialog opens.
_require_design and _design are patched to return a mock design.
_validate_parameter_name_response is partially tested here via the integration path;
unit tests for it live in test_parameter_name.py.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import BetterParameters as bp
from helpers import make_mock_design, make_package_json, make_param_record


def write_package(tmp_path, records, **pkg_kwargs):
    p = tmp_path / "pkg.bpmeta.json"
    p.write_text(make_package_json(records, **pkg_kwargs), encoding="utf-8")
    return str(p)


def validate(tmp_path, records, existing_names=None, conflict_policy="skip",
             apply_expressions_units=False, apply_comments=True,
             apply_groups=True, apply_favorites=True, apply_order=False,
             **pkg_kwargs):
    """Run _validate_parameters_package_import with a canned package file and mock design."""
    file_path = write_package(tmp_path, records, **pkg_kwargs)
    mock_design = make_mock_design([{"name": n} for n in (existing_names or [])])
    data = {
        "filePath": file_path,
        "conflictPolicy": conflict_policy,
        "applyExpressionsUnits": apply_expressions_units,
        "applyComments": apply_comments,
        "applyGroups": apply_groups,
        "applyFavorites": apply_favorites,
        "applyOrder": apply_order,
    }
    with patch.object(bp, "_require_design", return_value=mock_design):
        with patch.object(bp, "_design", return_value=mock_design):
            return bp._validate_parameters_package_import(data)


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

class TestValidatePackageBasics:
    def test_ok_true_on_valid_package(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")])
        assert result["ok"] is True
        assert result["cancelled"] is False

    def test_preview_present(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")])
        assert "preview" in result
        assert result["preview"] is not None

    def test_file_path_returned(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")])
        assert result["filePath"].endswith(".bpmeta.json")

    def test_state_always_null(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")])
        assert result.get("state") is None


# ---------------------------------------------------------------------------
# add_count — new parameters
# ---------------------------------------------------------------------------

class TestValidateAddCount:
    def test_single_new_param(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")])
        assert result["preview"]["addCount"] == 1

    def test_multiple_new_params(self, tmp_path):
        records = [make_param_record("a"), make_param_record("b"), make_param_record("c")]
        result = validate(tmp_path, records)
        assert result["preview"]["addCount"] == 3

    def test_new_and_existing_counts_split(self, tmp_path):
        records = [make_param_record("width"), make_param_record("height")]
        result = validate(tmp_path, records, existing_names=["width"], conflict_policy="overwrite")
        assert result["preview"]["addCount"] == 1
        assert result["preview"]["updateCount"] == 1


# ---------------------------------------------------------------------------
# skip_count — existing parameters with skip policy
# ---------------------------------------------------------------------------

class TestValidateSkipCount:
    def test_existing_with_skip_policy(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")], existing_names=["width"])
        assert result["preview"]["skipCount"] == 1
        assert result["preview"]["updateCount"] == 0

    def test_all_skipped(self, tmp_path):
        records = [make_param_record("a"), make_param_record("b")]
        result = validate(tmp_path, records, existing_names=["a", "b"], conflict_policy="skip")
        assert result["preview"]["skipCount"] == 2
        assert result["preview"]["addCount"] == 0


# ---------------------------------------------------------------------------
# update_count — existing parameters with overwrite/merge-safe policies
# ---------------------------------------------------------------------------

class TestValidateUpdateCount:
    def test_existing_with_overwrite_policy(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")],
                          existing_names=["width"], conflict_policy="overwrite")
        assert result["preview"]["updateCount"] == 1
        assert result["preview"]["skipCount"] == 0

    def test_existing_with_merge_safe_policy(self, tmp_path):
        result = validate(tmp_path, [make_param_record("width")],
                          existing_names=["width"], conflict_policy="merge-safe")
        assert result["preview"]["updateCount"] == 1

    def test_multiple_existing_overwrite(self, tmp_path):
        records = [make_param_record("a"), make_param_record("b"), make_param_record("c")]
        result = validate(tmp_path, records, existing_names=["a", "b"], conflict_policy="overwrite")
        assert result["preview"]["updateCount"] == 2
        assert result["preview"]["addCount"] == 1


# ---------------------------------------------------------------------------
# failedRows — definite failures
# ---------------------------------------------------------------------------

class TestValidateFailedRows:
    def test_missing_name_fails(self, tmp_path):
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = validate(tmp_path, records)
        assert len(result["preview"]["failedRows"]) == 1
        assert result["preview"]["addCount"] == 0

    def test_missing_expression_for_new_param_fails(self, tmp_path):
        records = [{"name": "width", "expression": "", "unit": "mm"}]
        result = validate(tmp_path, records)
        assert any("expression" in r["message"].lower() for r in result["preview"]["failedRows"])

    def test_duplicate_name_in_package_fails_second(self, tmp_path):
        records = [make_param_record("width"), make_param_record("width")]
        result = validate(tmp_path, records)
        failed = result["preview"]["failedRows"]
        assert len(failed) == 1
        assert "duplicate" in failed[0]["message"].lower()
        # First occurrence counted as add, second as fail
        assert result["preview"]["addCount"] == 1

    def test_invalid_parameter_name_fails(self, tmp_path):
        records = [{"name": "1bad", "expression": "10 mm", "unit": "mm"}]
        result = validate(tmp_path, records)
        assert len(result["preview"]["failedRows"]) >= 1

    def test_failed_row_has_row_number(self, tmp_path):
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = validate(tmp_path, records)
        assert result["preview"]["failedRows"][0]["row"] == 1

    def test_failed_row_has_name_field(self, tmp_path):
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = validate(tmp_path, records)
        assert "name" in result["preview"]["failedRows"][0]

    def test_failed_row_has_message_field(self, tmp_path):
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = validate(tmp_path, records)
        assert result["preview"]["failedRows"][0]["message"] != ""

    def test_good_rows_not_affected_by_bad_row(self, tmp_path):
        records = [
            {"name": "", "expression": "10 mm", "unit": "mm"},
            make_param_record("height"),
        ]
        result = validate(tmp_path, records)
        assert result["preview"]["addCount"] == 1
        assert len(result["preview"]["failedRows"]) == 1


# ---------------------------------------------------------------------------
# warnings / potentialFailCount — expression validation
# ---------------------------------------------------------------------------

class TestValidateWarnings:
    def test_expression_warning_for_existing_with_apply_expressions(self, tmp_path):
        """When applyExpressionsUnits=True and expression fails validation, should warn."""
        records = [make_param_record("width", expression="bad_expression_xyz")]
        mock_design = make_mock_design([{"name": "width"}])
        # Make expression validation fail
        mock_design.unitsManager.isValidExpression.return_value = False
        file_path = write_package(tmp_path, records)
        data = {
            "filePath": file_path,
            "conflictPolicy": "overwrite",
            "applyExpressionsUnits": True,
        }
        with patch.object(bp, "_require_design", return_value=mock_design):
            with patch.object(bp, "_design", return_value=mock_design):
                result = bp._validate_parameters_package_import(data)
        assert result["preview"]["potentialFailCount"] >= 1
        assert len(result["preview"]["warnings"]) >= 1

    def test_no_warning_when_apply_expressions_false(self, tmp_path):
        """When applyExpressionsUnits=False, no expression warnings for existing params."""
        records = [make_param_record("width", expression="bad_xyz")]
        result = validate(tmp_path, records, existing_names=["width"],
                          conflict_policy="overwrite", apply_expressions_units=False)
        assert result["preview"]["potentialFailCount"] == 0

    def test_missing_expression_with_apply_expressions_warns(self, tmp_path):
        """Existing param + applyExpressionsUnits=True + empty expression in package → warning."""
        records = [{"name": "width", "expression": "", "unit": "mm"}]
        mock_design = make_mock_design([{"name": "width"}])
        file_path = write_package(tmp_path, records)
        data = {
            "filePath": file_path,
            "conflictPolicy": "overwrite",
            "applyExpressionsUnits": True,
        }
        with patch.object(bp, "_require_design", return_value=mock_design):
            with patch.object(bp, "_design", return_value=mock_design):
                result = bp._validate_parameters_package_import(data)
        assert result["preview"]["potentialFailCount"] >= 1


# ---------------------------------------------------------------------------
# Empty package
# ---------------------------------------------------------------------------

def test_empty_package_all_zeros(tmp_path):
    result = validate(tmp_path, [])
    p = result["preview"]
    assert p["addCount"] == 0
    assert p["updateCount"] == 0
    assert p["skipCount"] == 0
    assert p["potentialFailCount"] == 0
    assert p["warnings"] == []
    assert p["failedRows"] == []


# ---------------------------------------------------------------------------
# Bad package file (parse error)
# ---------------------------------------------------------------------------

def test_invalid_json_raises(tmp_path):
    bad_path = str(tmp_path / "bad.bpmeta.json")
    Path(bad_path).write_text("not json", encoding="utf-8")
    mock_design = make_mock_design()
    data = {"filePath": bad_path, "conflictPolicy": "skip"}
    with patch.object(bp, "_require_design", return_value=mock_design):
        with patch.object(bp, "_design", return_value=mock_design):
            with pytest.raises(ValueError, match="JSON parse error"):
                bp._validate_parameters_package_import(data)


def test_schema_version_too_new_raises(tmp_path):
    file_path = write_package(tmp_path, [], schema_version=9999)
    mock_design = make_mock_design()
    data = {"filePath": file_path, "conflictPolicy": "skip"}
    with patch.object(bp, "_require_design", return_value=mock_design):
        with patch.object(bp, "_design", return_value=mock_design):
            with pytest.raises(ValueError, match="newer than supported"):
                bp._validate_parameters_package_import(data)
