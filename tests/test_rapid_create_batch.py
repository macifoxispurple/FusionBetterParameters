import BetterParameters as BP
from helpers import make_mock_design
from unittest.mock import patch


def _design_with_existing():
    design = make_mock_design([
        {"name": "width", "expression": "10 mm", "unit": "mm", "comment": "old"},
        {"name": "height", "expression": "20 mm", "unit": "mm", "comment": "old"},
    ])
    params = {
        "tok_width": design.userParameters.itemByName("width"),
        "tok_height": design.userParameters.itemByName("height"),
    }
    return design, params


def test_rapid_create_validate_batch_reports_duplicate_and_missing_expression():
    design, params = _design_with_existing()
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", side_effect=lambda _design, token: params.get(token)):
        result = BP._rapid_create_validate_batch({
            "rows": [
                {"rowId": "r1", "targetName": "newWidth", "expression": "", "unit": "mm", "operation": "create"},
                {"rowId": "r2", "targetName": "newWidth", "expression": "15 mm", "unit": "mm", "operation": "create"},
            ]
        })
    assert result["ok"] is False
    assert result["blockingCount"] == 2
    assert any("Duplicate target name" in item["message"] for row in result["rows"] for item in row["diagnostics"])
    assert any("Expression is required." in item["message"] for row in result["rows"] for item in row["diagnostics"])


def test_rapid_create_preview_batch_is_read_only():
    design, params = _design_with_existing()
    width = params["tok_width"]
    before_name = width.name
    before_expression = width.expression
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", side_effect=lambda _design, token: params.get(token)):
        result = BP._rapid_create_preview_batch({
            "rows": [
                {"rowId": "r1", "matchedParameterKey": "tok_width", "currentName": "width", "targetName": "width", "expression": "42 mm", "unit": "mm", "operation": "update"},
            ]
        })
    assert result["ok"] is True
    assert result["rows"][0]["preview"]
    assert width.name == before_name
    assert width.expression == before_expression


def test_rapid_create_apply_batch_orders_creates_by_dependency():
    design, params = _design_with_existing()
    create_calls = []
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", side_effect=lambda _design, token: params.get(token)), \
         patch.object(BP, "_create_parameter", side_effect=lambda payload: create_calls.append(payload["name"])), \
         patch.object(BP, "_rename_parameter", return_value=None), \
         patch.object(BP, "_batch_update_parameters", return_value={"ok": True, "updatedCount": 0, "failedRows": [], "message": ""}):
        result = BP._rapid_create_apply_batch({
            "rows": [
                {"rowId": "r1", "targetName": "outerWidth", "expression": "innerWidth * 2", "unit": "mm", "operation": "create"},
                {"rowId": "r2", "targetName": "innerWidth", "expression": "5 mm", "unit": "mm", "operation": "create"},
            ]
        })
    assert result["ok"] is True
    assert create_calls == ["innerWidth", "outerWidth"]
    assert result["counts"]["create"] == 2


def test_rapid_create_apply_batch_renames_then_updates_existing_rows():
    design, params = _design_with_existing()
    rename_calls = []
    update_calls = []

    def _fake_batch_update(payload):
        update_calls.extend(payload["updates"])
        return {"ok": True, "updatedCount": len(payload["updates"]), "failedRows": [], "message": ""}

    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_find_user_parameter_by_token", side_effect=lambda _design, token: params.get(token)), \
         patch.object(BP, "_rename_parameter", side_effect=lambda payload: rename_calls.append((payload["name"], payload["newName"])) or setattr(params["tok_width"], "name", payload["newName"])), \
         patch.object(BP, "_batch_update_parameters", side_effect=_fake_batch_update), \
         patch.object(BP, "_parameter_entity_token", side_effect=lambda param: "tok_width" if param is params["tok_width"] else "tok_height"):
        result = BP._rapid_create_apply_batch({
            "rows": [
                {"rowId": "r1", "matchedParameterKey": "tok_width", "currentName": "width", "targetName": "widthRenamed", "expression": "42 mm", "unit": "mm", "comment": "renamed", "operation": "rename"},
                {"rowId": "r2", "matchedParameterKey": "tok_height", "currentName": "height", "targetName": "height", "expression": "84 mm", "unit": "mm", "comment": "updated", "operation": "update"},
            ]
        })
    assert result["ok"] is True
    assert rename_calls == [("width", "widthRenamed")]
    assert [item["name"] for item in update_calls] == ["widthRenamed", "height"]
    assert result["counts"]["rename"] == 1
    assert result["counts"]["update"] == 1
