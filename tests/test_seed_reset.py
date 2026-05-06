"""
test_seed_reset.py — verify _seed_test_parameters and _reset_test_state logic.
"""
import pytest
from unittest.mock import MagicMock, patch, call
import BetterParameters as BP
from helpers import make_mock_design


_PREFIX = BP._BPTEST_PREFIX  # "_bptest_"


# ---------------------------------------------------------------------------
# _seed_test_parameters — prefix enforcement
# ---------------------------------------------------------------------------

def test_seed_adds_prefix_to_plain_name():
    """Name without prefix gets it added before creating the parameter."""
    created = MagicMock()
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    design.userParameters.add.return_value = created

    records = [{"name": "mywidth", "expression": "5 mm", "unit": "mm"}]
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_set_parameter_group"):
        result = BP._seed_test_parameters({"parameters": records})

    assert result["ok"]
    assert result["seededCount"] == 1
    # Verify add was called with the prefixed name
    call_args = design.userParameters.add.call_args
    assert call_args[0][0] == _PREFIX + "mywidth"


def test_seed_preserves_existing_prefix():
    """Name already starting with prefix is not double-prefixed."""
    created = MagicMock()
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    design.userParameters.add.return_value = created

    records = [{"name": _PREFIX + "mywidth", "expression": "5 mm", "unit": "mm"}]
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_set_parameter_group"):
        result = BP._seed_test_parameters({"parameters": records})

    call_args = design.userParameters.add.call_args
    assert call_args[0][0] == _PREFIX + "mywidth"  # exactly one prefix


# ---------------------------------------------------------------------------
# _seed_test_parameters — create vs update
# ---------------------------------------------------------------------------

def test_seed_creates_new_param():
    created = MagicMock()
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    design.userParameters.add.return_value = created

    records = [{"name": "alpha", "expression": "10 mm", "unit": "mm"}]
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_set_parameter_group"):
        result = BP._seed_test_parameters({"parameters": records})

    design.userParameters.add.assert_called_once()
    assert result["seededCount"] == 1


def test_seed_updates_existing_param():
    existing = MagicMock()
    existing.name = _PREFIX + "alpha"
    design = make_mock_design([])
    # side_effect takes precedence over return_value; reset it for full control
    prefixed_name = _PREFIX + "alpha"
    design.userParameters.itemByName.side_effect = lambda n: existing if n == prefixed_name else None

    records = [{"name": "alpha", "expression": "99 mm", "unit": "mm"}]
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_set_parameter_group"):
        result = BP._seed_test_parameters({"parameters": records})

    # Should update expression, not call add
    assert existing.expression == "99 mm"
    design.userParameters.add.assert_not_called()
    assert result["seededCount"] == 1


# ---------------------------------------------------------------------------
# _seed_test_parameters — validation failures
# ---------------------------------------------------------------------------

def test_seed_empty_name_fails():
    design = make_mock_design([])
    records = [{"name": "", "expression": "5 mm", "unit": "mm"}]
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design):
        result = BP._seed_test_parameters({"parameters": records})
    assert result["failedRows"][0]["message"] == "Name is required."


def test_seed_empty_expression_fails():
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    records = [{"name": "beta", "expression": "", "unit": "mm"}]
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design):
        result = BP._seed_test_parameters({"parameters": records})
    assert len(result["failedRows"]) == 1
    assert "Expression" in result["failedRows"][0]["message"]


def test_seed_non_list_parameters_raises():
    design = make_mock_design([])
    with patch.object(BP, "_require_design", return_value=design):
        with pytest.raises(BP.BPValidationError):
            BP._seed_test_parameters({"parameters": "notalist"})


def test_seed_empty_list_ok():
    design = make_mock_design([])
    with patch.object(BP, "_require_design", return_value=design):
        result = BP._seed_test_parameters({"parameters": []})
    assert result["ok"]
    assert result["seededCount"] == 0


# ---------------------------------------------------------------------------
# _seed_test_parameters — group applied
# ---------------------------------------------------------------------------

def test_seed_applies_group_when_provided():
    created = MagicMock()
    design = make_mock_design([])
    design.userParameters.itemByName.return_value = None
    design.userParameters.add.return_value = created

    records = [{"name": "gamma", "expression": "1 mm", "unit": "mm", "group": "TestGroup"}]
    with patch.object(BP, "_require_design", return_value=design), \
         patch.object(BP, "_design", return_value=design), \
         patch.object(BP, "_set_parameter_group") as mock_set_group:
        BP._seed_test_parameters({"parameters": records})

    mock_set_group.assert_called_once()
    call_data = mock_set_group.call_args[0][0]
    assert call_data["group"] == "TestGroup"


# ---------------------------------------------------------------------------
# _reset_test_state — confirm guard
# ---------------------------------------------------------------------------

def test_reset_requires_confirm_reset():
    design = make_mock_design([])
    with patch.object(BP, "_require_design", return_value=design):
        with pytest.raises(BP.BPValidationError):
            BP._reset_test_state({"confirm": "yes"})


def test_reset_requires_exact_reset_string():
    design = make_mock_design([])
    with patch.object(BP, "_require_design", return_value=design):
        with pytest.raises(BP.BPValidationError):
            BP._reset_test_state({"confirm": "reset"})  # lowercase


def test_reset_missing_confirm_raises():
    design = make_mock_design([])
    with patch.object(BP, "_require_design", return_value=design):
        with pytest.raises(BP.BPValidationError):
            BP._reset_test_state({})


# ---------------------------------------------------------------------------
# _reset_test_state — deletion
# ---------------------------------------------------------------------------

def _make_param_mock(name):
    p = MagicMock()
    p.name = name
    return p


def test_reset_deletes_bptest_params():
    p1 = _make_param_mock(_PREFIX + "foo")
    p2 = _make_param_mock(_PREFIX + "bar")
    p3 = _make_param_mock("normal_param")  # should NOT be deleted
    param_list = [p1, p2, p3]

    design = MagicMock()
    design.userParameters.count = len(param_list)
    design.userParameters.item.side_effect = lambda i: param_list[i] if 0 <= i < len(param_list) else None
    design.userParameters.itemByName.side_effect = lambda n: next((p for p in param_list if p.name == n), None)

    with patch.object(BP, "_require_design", return_value=design):
        result = BP._reset_test_state({"confirm": "RESET"})

    assert result["ok"]
    assert result["clearedCount"] == 2
    p1.deleteMe.assert_called_once()
    p2.deleteMe.assert_called_once()
    p3.deleteMe.assert_not_called()


def test_reset_no_bptest_params_clears_zero():
    p1 = _make_param_mock("width")
    p2 = _make_param_mock("height")
    param_list = [p1, p2]

    design = MagicMock()
    design.userParameters.count = len(param_list)
    design.userParameters.item.side_effect = lambda i: param_list[i] if 0 <= i < len(param_list) else None
    design.userParameters.itemByName.side_effect = lambda n: next((p for p in param_list if p.name == n), None)

    with patch.object(BP, "_require_design", return_value=design):
        result = BP._reset_test_state({"confirm": "RESET"})

    assert result["ok"]
    assert result["clearedCount"] == 0


def test_reset_returns_ok_true():
    design = MagicMock()
    design.userParameters.count = 0
    design.userParameters.item.side_effect = lambda i: None

    with patch.object(BP, "_require_design", return_value=design):
        result = BP._reset_test_state({"confirm": "RESET"})

    assert result["ok"] is True
