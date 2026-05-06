"""
test_parameter_name.py — tests for _validate_parameter_name_response.

The function's last step checks design.allParameters for name collision.
We patch _design() to return None so that check is skipped (no design available),
testing only the offline structural validation rules.
"""
from unittest.mock import patch
import BetterParameters as bp


def validate(name):
    """Call _validate_parameter_name_response with no live design."""
    with patch.object(bp, "_design", return_value=None):
        return bp._validate_parameter_name_response(name)


# ---------------------------------------------------------------------------
# Empty / whitespace
# ---------------------------------------------------------------------------

def test_empty_string_fails():
    result = validate("")
    assert result["ok"] is False
    assert result["message"] != ""


def test_none_fails():
    result = validate(None)
    assert result["ok"] is False


def test_whitespace_only_fails():
    result = validate("   ")
    assert result["ok"] is False


def test_leading_whitespace_fails():
    result = validate(" width")
    assert result["ok"] is False
    assert "whitespace" in result["message"].lower()


def test_trailing_whitespace_fails():
    result = validate("width ")
    assert result["ok"] is False
    assert "whitespace" in result["message"].lower()


def test_internal_space_fails():
    result = validate("my param")
    assert result["ok"] is False
    assert "whitespace" in result["message"].lower() or "space" in result["message"].lower()


def test_tab_fails():
    result = validate("my\tparam")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Starts with digit
# ---------------------------------------------------------------------------

def test_starts_with_digit_fails():
    result = validate("1width")
    assert result["ok"] is False


def test_starts_with_digit_zero_fails():
    result = validate("0abc")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Invalid characters
# ---------------------------------------------------------------------------

def test_hyphen_fails():
    result = validate("my-param")
    assert result["ok"] is False


def test_at_sign_fails():
    result = validate("my@param")
    assert result["ok"] is False


def test_dot_fails():
    result = validate("my.param")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# Valid names
# ---------------------------------------------------------------------------

def test_simple_alpha_ok():
    result = validate("width")
    assert result["ok"] is True


def test_mixed_case_ok():
    result = validate("MyParam")
    assert result["ok"] is True


def test_with_underscore_ok():
    result = validate("my_param")
    assert result["ok"] is True


def test_starts_with_underscore_ok():
    result = validate("_private")
    assert result["ok"] is True


def test_alphanumeric_with_digit_after_start_ok():
    result = validate("param1")
    assert result["ok"] is True


def test_starts_with_dollar_ok():
    result = validate("$special")
    assert result["ok"] is True


def test_single_letter_ok():
    result = validate("x")
    assert result["ok"] is True


def test_all_digits_after_letter_ok():
    result = validate("a123456")
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Name collision (mocked design)
# ---------------------------------------------------------------------------

def test_collision_with_existing_parameter_fails():
    from unittest.mock import MagicMock
    mock_design = MagicMock()
    mock_design.allParameters.itemByName.return_value = MagicMock()  # non-None = exists
    with patch.object(bp, "_design", return_value=mock_design):
        result = bp._validate_parameter_name_response("width")
    assert result["ok"] is False
    assert "already exists" in result["message"]


def test_no_collision_with_no_design():
    result = validate("brand_new_param")
    assert result["ok"] is True
