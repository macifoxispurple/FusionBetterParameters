"""
test_find_by_token.py — verify _find_user_parameter_by_token and
_find_model_parameter_by_token work when findEntityByToken returns an
ObjectCollection (not a list/tuple).

Regression for: both functions had isinstance(found, (list, tuple)) guard
that always evaluated False for Fusion ObjectCollection, causing silent
fallthrough to None and key-based lookup failure for all actions.
"""
import pytest
from unittest.mock import MagicMock, patch
import BetterParameters as BP
from adsk.fusion import ObjectCollection


def _make_user_param(name="width"):
    import adsk.fusion as F
    p = F.UserParameter()
    p.name = name
    p.expression = "10 mm"
    p.unit = "mm"
    p.comment = ""
    p.isFavorite = False
    return p


def _make_model_param(name="d1"):
    import adsk.fusion as F
    p = F.ModelParameter()
    p.name = name
    p.expression = "5 mm"
    p.unit = "mm"
    p.comment = ""
    p.isFavorite = False
    return p


def _make_design_with_token(param, token="tok123"):
    design = MagicMock()
    collection = ObjectCollection([param])
    design.findEntityByToken.return_value = collection
    return design


# ---------------------------------------------------------------------------
# _find_user_parameter_by_token
# ---------------------------------------------------------------------------

def test_find_user_param_by_token_returns_param():
    param = _make_user_param("width")
    design = _make_design_with_token(param)
    result = BP._find_user_parameter_by_token(design, "tok123")
    assert result is param


def test_find_user_param_by_token_empty_collection_returns_none():
    design = MagicMock()
    design.findEntityByToken.return_value = ObjectCollection([])
    result = BP._find_user_parameter_by_token(design, "tok123")
    assert result is None


def test_find_user_param_by_token_wrong_type_in_collection_returns_none():
    """Collection contains a ModelParameter — cast to UserParameter should fail."""
    model_param = _make_model_param("d1")
    design = _make_design_with_token(model_param)
    result = BP._find_user_parameter_by_token(design, "tok123")
    assert result is None


def test_find_user_param_no_token_returns_none():
    design = MagicMock()
    assert BP._find_user_parameter_by_token(design, "") is None
    assert BP._find_user_parameter_by_token(design, None) is None


def test_find_user_param_no_design_returns_none():
    assert BP._find_user_parameter_by_token(None, "tok") is None


def test_find_user_param_findEntityByToken_raises_returns_none():
    design = MagicMock()
    design.findEntityByToken.side_effect = RuntimeError("Fusion error")
    result = BP._find_user_parameter_by_token(design, "tok123")
    assert result is None


def test_find_user_param_list_fallback_still_works():
    """Defensive: if findEntityByToken ever returns a real list, still works."""
    param = _make_user_param("height")
    design = MagicMock()
    design.findEntityByToken.return_value = [param]
    result = BP._find_user_parameter_by_token(design, "tok123")
    assert result is param


# ---------------------------------------------------------------------------
# _find_model_parameter_by_token
# ---------------------------------------------------------------------------

def test_find_model_param_by_token_returns_param():
    param = _make_model_param("d1")
    design = _make_design_with_token(param)
    result = BP._find_model_parameter_by_token(design, "tok123")
    assert result is param


def test_find_model_param_by_token_empty_collection_returns_none():
    design = MagicMock()
    design.findEntityByToken.return_value = ObjectCollection([])
    result = BP._find_model_parameter_by_token(design, "tok123")
    assert result is None


def test_find_model_param_wrong_type_returns_none():
    """Collection contains a UserParameter — cast to ModelParameter should fail."""
    user_param = _make_user_param("width")
    design = _make_design_with_token(user_param)
    result = BP._find_model_parameter_by_token(design, "tok123")
    assert result is None


def test_find_model_param_no_token_returns_none():
    design = MagicMock()
    assert BP._find_model_parameter_by_token(design, "") is None
    assert BP._find_model_parameter_by_token(design, None) is None


def test_find_model_param_no_design_returns_none():
    assert BP._find_model_parameter_by_token(None, "tok") is None


def test_find_model_param_findEntityByToken_raises_returns_none():
    design = MagicMock()
    design.findEntityByToken.side_effect = RuntimeError("Fusion error")
    result = BP._find_model_parameter_by_token(design, "tok123")
    assert result is None


# ---------------------------------------------------------------------------
# Regression: the old isinstance(found, (list, tuple)) guard was wrong
# ---------------------------------------------------------------------------

def test_object_collection_is_not_list_or_tuple():
    """Confirm ObjectCollection is not a list/tuple — this was the root cause."""
    col = ObjectCollection([_make_user_param()])
    assert not isinstance(col, (list, tuple))


def test_object_collection_is_iterable():
    """ObjectCollection must be iterable for the fix to work."""
    param = _make_user_param("x")
    col = ObjectCollection([param])
    items = list(col)
    assert items == [param]
