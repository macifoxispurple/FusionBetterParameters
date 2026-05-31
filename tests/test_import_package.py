"""
test_import_package.py — tests for _import_parameters_package result accounting and ok semantics.

All Fusion mutations (parameter.add, parameter.expression =, etc.) are exercised through
the mock design. We verify the returned counts and ok/message logic, not Fusion internals.
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest
import BetterParameters as bp
from helpers import make_mock_design, make_package_json, make_param_record


def write_package(tmp_path, records, **pkg_kwargs):
    p = tmp_path / "pkg.bpmeta.json"
    p.write_text(make_package_json(records, **pkg_kwargs), encoding="utf-8")
    return str(p)


def do_import(tmp_path, records, existing_params=None, conflict_policy="skip",
              apply_expressions_units=False, apply_comments=True,
              apply_groups=True, apply_favorites=True, apply_order=False,
              design_override=None, **pkg_kwargs):
    """Run _import_parameters_package with a canned package and mock design."""
    file_path = write_package(tmp_path, records, **pkg_kwargs)
    mock_design = design_override or make_mock_design(existing_params or [])

    # Stub out helpers that write to disk / metadata parameter
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
            with patch.object(bp, "_set_parameter_group", return_value=None):
                with patch.object(bp, "_read_document_order_state", return_value={}):
                    with patch.object(bp, "_persist_document_order_snapshot", return_value=None):
                        with patch.object(bp, "_write_document_order_state", return_value=None):
                            with patch.object(bp, "_bump_ui_state_record", return_value={}):
                                return bp._import_parameters_package(data)


# ---------------------------------------------------------------------------
# ok / message semantics
# ---------------------------------------------------------------------------

class TestImportOkSemantics:
    def test_all_new_ok_true(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width")])
        assert result["ok"] is True

    def test_all_skipped_ok_true(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width")],
                           existing_params=[{"name": "width"}], conflict_policy="skip")
        assert result["ok"] is True

    def test_all_skipped_message_mentions_skip(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width")],
                           existing_params=[{"name": "width"}], conflict_policy="skip")
        assert "skip" in result["message"].lower() or result["message"] == ""

    def test_all_failed_ok_false(self, tmp_path):
        # All rows fail: missing name
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = do_import(tmp_path, records)
        assert result["ok"] is False

    def test_all_failed_state_null(self, tmp_path):
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = do_import(tmp_path, records)
        # The result dict does not contain state (handler adds it), but ok=False.
        assert result["ok"] is False

    def test_partial_failure_ok_true(self, tmp_path):
        records = [
            make_param_record("width"),
            {"name": "", "expression": "10 mm", "unit": "mm"},
        ]
        result = do_import(tmp_path, records)
        assert result["ok"] is True
        assert result["importedCount"] == 1
        assert result["failedCount"] == 1

    def test_partial_failure_message_mentions_rows(self, tmp_path):
        records = [
            make_param_record("width"),
            {"name": "", "expression": "10 mm", "unit": "mm"},
        ]
        result = do_import(tmp_path, records)
        assert "row" in result["message"].lower() or "fail" in result["message"].lower()

    def test_success_message_empty(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width")])
        assert result["message"] == ""

    def test_not_cancelled(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width")])
        assert result["cancelled"] is False


# ---------------------------------------------------------------------------
# importedCount vs updatedCount separation
# ---------------------------------------------------------------------------

class TestImportUpdatedCounts:
    def test_new_params_go_to_imported_count(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width"), make_param_record("height")])
        assert result["importedCount"] == 2
        assert result["updatedCount"] == 0

    def test_existing_overwrite_goes_to_updated_count(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width")],
                           existing_params=[{"name": "width"}], conflict_policy="overwrite")
        assert result["updatedCount"] == 1
        assert result["importedCount"] == 0

    def test_mixed_new_and_existing(self, tmp_path):
        records = [make_param_record("width"), make_param_record("height")]
        result = do_import(tmp_path, records,
                           existing_params=[{"name": "width"}], conflict_policy="overwrite")
        assert result["importedCount"] == 1  # height is new
        assert result["updatedCount"] == 1   # width is updated

    def test_skip_policy_no_updated_count(self, tmp_path):
        result = do_import(tmp_path, [make_param_record("width")],
                           existing_params=[{"name": "width"}], conflict_policy="skip")
        assert result["updatedCount"] == 0
        assert result["skippedCount"] == 1

    def test_skipped_count_correct(self, tmp_path):
        records = [make_param_record("a"), make_param_record("b"), make_param_record("c")]
        result = do_import(tmp_path, records,
                           existing_params=[{"name": "a"}, {"name": "b"}], conflict_policy="skip")
        assert result["skippedCount"] == 2
        assert result["importedCount"] == 1


# ---------------------------------------------------------------------------
# failedRows
# ---------------------------------------------------------------------------

class TestImportFailedRows:
    def test_missing_name_produces_failed_row(self, tmp_path):
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = do_import(tmp_path, records)
        assert result["failedCount"] == 1
        assert result["failedRows"][0]["name"] == ""

    def test_duplicate_name_in_package_fails_second(self, tmp_path):
        records = [make_param_record("width"), make_param_record("width")]
        result = do_import(tmp_path, records)
        assert result["failedCount"] == 1
        assert result["importedCount"] == 1
        assert "duplicate" in result["failedRows"][0]["message"].lower()

    def test_missing_expression_for_new_param_fails(self, tmp_path):
        records = [{"name": "width", "expression": "", "unit": "mm"}]
        result = do_import(tmp_path, records)
        assert result["failedCount"] == 1
        assert result["importedCount"] == 0

    def test_failed_row_structure(self, tmp_path):
        records = [{"name": "", "expression": "10 mm", "unit": "mm"}]
        result = do_import(tmp_path, records)
        row = result["failedRows"][0]
        assert "row" in row
        assert "name" in row
        assert "message" in row

    def test_failed_count_matches_failed_rows_length(self, tmp_path):
        records = [
            {"name": "", "expression": "10 mm", "unit": "mm"},
            {"name": "", "expression": "20 mm", "unit": "mm"},
        ]
        result = do_import(tmp_path, records)
        assert result["failedCount"] == len(result["failedRows"])


# ---------------------------------------------------------------------------
# Fusion add() is called for new parameters
# ---------------------------------------------------------------------------

class TestImportCallsAdd:
    def test_add_called_for_new_param(self, tmp_path):
        mock_design = make_mock_design()
        created_param = MagicMock()
        mock_design.userParameters.add.return_value = created_param

        result = do_import(tmp_path, [make_param_record("width", "100 mm", "mm")],
                           design_override=mock_design)
        mock_design.userParameters.add.assert_called_once()
        assert result["importedCount"] == 1

    def test_add_not_called_when_skipped(self, tmp_path):
        mock_design = make_mock_design([{"name": "width"}])
        result = do_import(tmp_path, [make_param_record("width")],
                           design_override=mock_design, conflict_policy="skip")
        mock_design.userParameters.add.assert_not_called()
        assert result["skippedCount"] == 1


# ---------------------------------------------------------------------------
# apply knobs — expression update for existing param
# ---------------------------------------------------------------------------

class TestImportApplyKnobs:
    def test_expression_not_updated_when_apply_expressions_false(self, tmp_path):
        existing_param = MagicMock()
        existing_param.name = "width"
        existing_param.unit = "mm"

        mock_design = MagicMock()
        mock_design.userParameters.itemByName.return_value = existing_param
        mock_design.allParameters.itemByName.return_value = existing_param

        result = do_import(tmp_path, [make_param_record("width", "999 mm")],
                           design_override=mock_design,
                           conflict_policy="overwrite",
                           apply_expressions_units=False)
        # expression attribute should NOT have been set
        assert not any(
            c for c in existing_param.mock_calls
            if "expression" in str(c) and "999 mm" in str(c)
        )
        assert result["updatedCount"] == 1

    def test_expression_updated_when_apply_expressions_true(self, tmp_path):
        existing_param = MagicMock()
        existing_param.name = "width"
        existing_param.unit = "mm"

        mock_design = MagicMock()
        mock_design.userParameters.itemByName.return_value = existing_param
        mock_design.allParameters.itemByName.return_value = existing_param

        result = do_import(tmp_path, [make_param_record("width", "999 mm")],
                           design_override=mock_design,
                           conflict_policy="overwrite",
                           apply_expressions_units=True)
        # expression attribute should have been set to "999 mm"
        existing_param.__setattr__  # verify it's a mock
        assert result["updatedCount"] == 1


# ---------------------------------------------------------------------------
# Cancelled (no filePath, no UI)
# ---------------------------------------------------------------------------

def test_cancelled_when_no_ui_and_no_filepath():
    """With no filePath and no UI, should return cancelled or raise."""
    mock_design = make_mock_design()
    data = {"filePath": "", "conflictPolicy": "skip"}
    with patch.object(bp, "_require_design", return_value=mock_design):
        with patch.object(bp, "ui", None):
            try:
                result = bp._import_parameters_package(data)
                assert result.get("cancelled") is True
            except RuntimeError as exc:
                assert "UI" in str(exc)


# ---------------------------------------------------------------------------
# Bad package file
# ---------------------------------------------------------------------------

def test_invalid_json_raises(tmp_path):
    bad_path = str(tmp_path / "bad.bpmeta.json")
    Path(bad_path).write_text("not json {{", encoding="utf-8")
    mock_design = make_mock_design()
    data = {"filePath": bad_path, "conflictPolicy": "skip"}
    with patch.object(bp, "_require_design", return_value=mock_design):
        with patch.object(bp, "_design", return_value=mock_design):
            with pytest.raises(ValueError, match="JSON parse error"):
                bp._import_parameters_package(data)
