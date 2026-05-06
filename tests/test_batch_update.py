"""
test_batch_update.py — offline tests for _batch_update_parameters.

Covers:
  - Happy path: all params found, modifyParameters called once, comments applied.
  - Empty updates list returns ok immediately.
  - Not-array updates raises BPValidationError.
  - Parameter not found → ok:False, NOT_FOUND, no mutation.
  - Sequential fallback (no modifyParameters on design).
  - modifyParameters returns False → ok:False, VALIDATION_ERROR.
  - modifyParameters raises → ok:False, UNKNOWN_ERROR.
  - comment=None leaves existing comment untouched.
  - comment="" clears the comment.
  - No design → raises BPNoDesignError.
"""
import pytest
from unittest.mock import MagicMock, patch, call
import BetterParameters as BP
from helpers import make_mock_design, make_mock_param
from adsk.fusion import ObjectCollection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_design_with_params(*specs):
    """Build a mock design where each spec is (name, expression, token).
    Params are resolvable by name via itemByName and by token via findEntityByToken.
    """
    design = MagicMock()
    params_by_name = {}
    params_by_token = {}

    for spec in specs:
        name, expression, token = spec
        p = make_mock_param(name=name, expression=expression)
        params_by_name[name] = p
        params_by_token[token] = p

    def item_by_name(n):
        return params_by_name.get(n)

    def find_by_token(t):
        param = params_by_token.get(t)
        return ObjectCollection([param] if param else [])

    design.userParameters.itemByName.side_effect = item_by_name
    design.findEntityByToken.side_effect = find_by_token
    # modifyParameters returns True by default
    design.modifyParameters.return_value = True
    return design, params_by_name


def _call(design, updates):
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        return BP._batch_update_parameters({"updates": updates})


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_ok_and_count():
    design, params = _make_design_with_params(
        ("width", "10 mm", "tok_w"),
        ("height", "20 mm", "tok_h"),
    )
    result = _call(design, [
        {"key": "tok_w", "name": "width",  "expression": "50 mm", "comment": "w"},
        {"key": "tok_h", "name": "height", "expression": "80 mm", "comment": "h"},
    ])
    assert result["ok"] is True
    assert result["updatedCount"] == 2
    assert result["failedRows"] == []


def test_happy_path_modify_parameters_called_once():
    """modifyParameters must be called exactly once with both params — single recompute."""
    design, params = _make_design_with_params(
        ("width", "10 mm", "tok_w"),
        ("height", "20 mm", "tok_h"),
    )
    _call(design, [
        {"key": "tok_w", "name": "width",  "expression": "50 mm"},
        {"key": "tok_h", "name": "height", "expression": "80 mm"},
    ])
    assert design.modifyParameters.call_count == 1
    call_args = design.modifyParameters.call_args
    assert len(call_args[0][0]) == 2   # two params
    assert len(call_args[0][1]) == 2   # two values


def test_happy_path_comments_applied():
    design, params = _make_design_with_params(("width", "10 mm", "tok_w"))
    _call(design, [{"key": "tok_w", "name": "width", "expression": "50 mm", "comment": "shelf"}])
    assert params["width"].comment == "shelf"


def test_comment_empty_string_clears_comment():
    design, params = _make_design_with_params(("width", "10 mm", "tok_w"))
    params["width"].comment = "old comment"
    _call(design, [{"key": "tok_w", "name": "width", "expression": "50 mm", "comment": ""}])
    assert params["width"].comment == ""


def test_comment_none_not_set():
    """comment=None means omit — existing .comment should not be touched."""
    design, params = _make_design_with_params(("width", "10 mm", "tok_w"))
    params["width"].comment = "keep me"
    _call(design, [{"key": "tok_w", "name": "width", "expression": "50 mm"}])
    # comment not in record → default None → should not write
    assert params["width"].comment == "keep me"


def test_name_fallback_when_no_key():
    """If key absent, fall back to name-based lookup."""
    design, params = _make_design_with_params(("width", "10 mm", "tok_w"))
    result = _call(design, [{"name": "width", "expression": "50 mm"}])
    assert result["ok"] is True
    assert result["updatedCount"] == 1


# ---------------------------------------------------------------------------
# Empty and validation guards
# ---------------------------------------------------------------------------

def test_empty_updates_returns_ok_immediately():
    design, _ = _make_design_with_params()
    result = _call(design, [])
    assert result["ok"] is True
    assert result["updatedCount"] == 0
    design.modifyParameters.assert_not_called()


def test_non_list_updates_raises_validation_error():
    design, _ = _make_design_with_params()
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        with pytest.raises(BP.BPValidationError):
            BP._batch_update_parameters({"updates": "bad"})


def test_non_list_updates_dict_raises():
    design, _ = _make_design_with_params()
    with patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_require_design", return_value=design):
        with pytest.raises(BP.BPValidationError):
            BP._batch_update_parameters({"updates": {"key": "x"}})


# ---------------------------------------------------------------------------
# Parameter not found
# ---------------------------------------------------------------------------

def test_missing_param_returns_not_found():
    design, _ = _make_design_with_params(("width", "10 mm", "tok_w"))
    result = _call(design, [
        {"key": "tok_w",    "name": "width",  "expression": "50 mm"},
        {"key": "tok_miss", "name": "ghost",  "expression": "99 mm"},
    ])
    assert result["ok"] is False
    assert result["errorCode"] == BP.ERROR_NOT_FOUND
    assert result["updatedCount"] == 0
    assert len(result["failedRows"]) == 1
    assert result["failedRows"][0]["name"] == "ghost"


def test_missing_param_no_mutation():
    """If any param not found, modifyParameters must NOT be called."""
    design, _ = _make_design_with_params(("width", "10 mm", "tok_w"))
    _call(design, [
        {"key": "tok_w",    "name": "width", "expression": "50 mm"},
        {"key": "tok_miss", "name": "ghost", "expression": "99 mm"},
    ])
    design.modifyParameters.assert_not_called()


# ---------------------------------------------------------------------------
# modifyParameters returns False
# ---------------------------------------------------------------------------

def test_modify_parameters_returns_false_gives_validation_error():
    design, _ = _make_design_with_params(("width", "10 mm", "tok_w"))
    design.modifyParameters.return_value = False
    result = _call(design, [{"key": "tok_w", "name": "width", "expression": "bad expr"}])
    assert result["ok"] is False
    assert result["errorCode"] == BP.ERROR_VALIDATION
    assert result["updatedCount"] == 0


# ---------------------------------------------------------------------------
# modifyParameters raises
# ---------------------------------------------------------------------------

def test_modify_parameters_raises_gives_unknown_error():
    design, _ = _make_design_with_params(("width", "10 mm", "tok_w"))
    design.modifyParameters.side_effect = RuntimeError("Fusion crashed")
    result = _call(design, [{"key": "tok_w", "name": "width", "expression": "50 mm"}])
    assert result["ok"] is False
    assert result["errorCode"] == BP.ERROR_UNKNOWN
    assert "Fusion crashed" in result["message"]


# ---------------------------------------------------------------------------
# Sequential fallback (no modifyParameters)
# ---------------------------------------------------------------------------

def test_sequential_fallback_when_no_modify_parameters():
    """If design has no modifyParameters, fall back to sequential .expression=."""
    design, params = _make_design_with_params(
        ("width", "10 mm", "tok_w"),
        ("height", "20 mm", "tok_h"),
    )
    del design.modifyParameters   # simulate older Fusion build

    result = _call(design, [
        {"key": "tok_w", "name": "width",  "expression": "50 mm"},
        {"key": "tok_h", "name": "height", "expression": "80 mm"},
    ])
    assert result["ok"] is True
    assert result["updatedCount"] == 2


# ---------------------------------------------------------------------------
# No design
# ---------------------------------------------------------------------------

def test_no_design_raises():
    with patch.object(BP, "_require_design", side_effect=BP.BPNoDesignError()):
        with pytest.raises(BP.BPNoDesignError):
            BP._batch_update_parameters({"updates": [{"name": "x", "expression": "1"}]})
