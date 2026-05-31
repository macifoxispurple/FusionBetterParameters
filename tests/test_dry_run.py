"""
test_dry_run.py — verify dry_run=True on _import_parameters produces correct
counts without mutating the design.
"""
from unittest.mock import MagicMock, patch
import BetterParameters as BP
from helpers import make_mock_design


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp_csv(tmp_path, content):
    p = tmp_path / "test.csv"
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# _import_parameters dry_run — new params
# ---------------------------------------------------------------------------

def test_dry_run_csv_new_param_counts_but_does_not_add(tmp_path):
    csv = "name,expression,unit,comment,group\nnewparam,5 mm,mm,,\n"
    path = _write_tmp_csv(tmp_path, csv)
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    design.unitsManager.isValidExpression.return_value = True
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._import_parameters({"filePath": path, "conflictPolicy": "skip"}, dry_run=True)
    assert result["ok"]
    assert result["importedCount"] == 1
    design.userParameters.add.assert_not_called()


def test_dry_run_csv_skip_conflict_still_skips(tmp_path):
    csv = "name,expression,unit,comment,group\nexisting,5 mm,mm,,\n"
    path = _write_tmp_csv(tmp_path, csv)
    existing_param = MagicMock()
    existing_param.name = "existing"
    existing_param.expression = "3 mm"
    design = make_mock_design([])
    # Must reset side_effect so return_value takes precedence
    design.userParameters.itemByName.side_effect = None
    design.userParameters.itemByName.return_value = existing_param
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._import_parameters({"filePath": path, "conflictPolicy": "skip"}, dry_run=True)
    assert result["skippedCount"] == 1
    assert result["importedCount"] == 0


def test_dry_run_csv_overwrite_counts_but_no_mutation(tmp_path):
    csv = "name,expression,unit,comment,group\nexisting,5 mm,mm,,\n"
    path = _write_tmp_csv(tmp_path, csv)
    existing_param = MagicMock()
    existing_param.name = "existing"
    design = make_mock_design([])
    design.userParameters.itemByName.side_effect = None
    design.userParameters.itemByName.return_value = existing_param
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._import_parameters({"filePath": path, "conflictPolicy": "overwrite"}, dry_run=True)
    assert result["importedCount"] == 1
    # dry_run: existing_param.expression must NOT have been set to "5 mm"
    # (MagicMock attr access creates a new mock, not the string "5 mm")
    assert str(existing_param.expression) != "5 mm"


def test_dry_run_csv_invalid_name_still_fails(tmp_path):
    csv = "name,expression,unit,comment,group\n1bad,5 mm,mm,,\n"
    path = _write_tmp_csv(tmp_path, csv)
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._import_parameters({"filePath": path}, dry_run=True)
    assert result["failedCount"] == 1
    assert result["importedCount"] == 0


def test_dry_run_false_calls_add(tmp_path):
    csv = "name,expression,unit,comment,group\nnewparam,5 mm,mm,,\n"
    path = _write_tmp_csv(tmp_path, csv)
    created_mock = MagicMock()
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    design.userParameters.add.return_value = created_mock
    design.unitsManager.isValidExpression.return_value = True
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._import_parameters({"filePath": path}, dry_run=False)
    assert result["importedCount"] == 1
    design.userParameters.add.assert_called_once()


# ---------------------------------------------------------------------------
# dryRun field reflected in dispatch-level responses (via returned dict shape)
# ---------------------------------------------------------------------------

def test_dry_run_flag_propagated_in_import_parameters_result(tmp_path):
    csv = "name,expression,unit,comment,group\nnewparam,5 mm,mm,,\n"
    path = _write_tmp_csv(tmp_path, csv)
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    design.unitsManager.isValidExpression.return_value = True
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        result = BP._import_parameters({"filePath": path}, dry_run=True)
    # The helper itself returns counts; dispatch adds dryRun to response envelope.
    # We just verify the helper returns ok=True with importedCount.
    assert result["ok"]
    assert result["importedCount"] == 1
