"""Tests for _mask_expression_literals and _validate_expression_response.

Run with:  python -m pytest tests/test_literal_masking.py -v

Pure helper tests run without Fusion 360.  _validate_expression_response tests
use lightweight monkey-patching to stub the Fusion API branches.
"""
import sys
import types
import os
import re
import pytest


# ---------------------------------------------------------------------------
# Recursive auto-attribute stub for adsk.*
# Any attribute access returns another AutoMock; calls return None.
# ---------------------------------------------------------------------------

class _AutoMock:
    """Stub that silently absorbs any attribute access, call, or base-class usage."""
    def __getattr__(self, name):
        return _AutoMock()
    def __call__(self, *a, **kw):
        return _AutoMock()
    def __bool__(self):
        return False
    def __iter__(self):
        return iter([])
    def __int__(self):
        return 0
    def __str__(self):
        return ""
    def __mro_entries__(self, bases):
        # Allow _AutoMock instances to be used as base classes in class definitions.
        return (object,)


def _install_adsk_stubs():
    # Module-level __getattr__ in Python 3.7+ receives only (name), not (self, name).
    _am_factory = lambda n: _AutoMock()  # noqa: E731

    adsk_mod = types.ModuleType("adsk")
    adsk_mod.__getattr__ = _am_factory

    core_mod = types.ModuleType("adsk.core")
    core_mod.__getattr__ = _am_factory

    fusion_mod = types.ModuleType("adsk.fusion")
    fusion_mod.__getattr__ = _am_factory

    adsk_mod.core = core_mod
    adsk_mod.fusion = fusion_mod

    sys.modules.setdefault("adsk", adsk_mod)
    sys.modules.setdefault("adsk.core", core_mod)
    sys.modules.setdefault("adsk.fusion", fusion_mod)


_install_adsk_stubs()

# Ensure BetterParameters directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import importlib
bp = importlib.import_module("BetterParameters")

_mask = bp._mask_expression_literals


# ---------------------------------------------------------------------------
# _mask_expression_literals — unit tests
# ---------------------------------------------------------------------------

class TestMaskLiterals:

    # ── double-quoted strings ────────────────────────────────────────────────

    def test_double_quoted_basic(self):
        masked, err = _mask('"hello world"')
        assert err is None
        assert masked == "0"
        assert not re.search('[A-Za-z_]', masked)

    def test_double_quoted_with_context(self):
        masked, err = _mask('if(x > 0; "yes"; "no")')
        assert err is None
        assert "yes" not in masked
        assert "no" not in masked
        assert "if" in masked
        assert "x" in masked

    def test_double_quoted_escaped_inner_quote(self):
        masked, err = _mask(r'"say \"hi\""')
        assert err is None
        assert masked == "0"

    def test_double_quoted_unclosed(self):
        masked, err = _mask('"unclosed')
        assert masked is None
        assert "Unclosed" in err

    def test_double_quoted_multi_literals(self):
        masked, err = _mask('"a" + "b"')
        assert err is None
        assert "a" not in masked
        assert "b" not in masked
        assert "+" in masked

    def test_double_quoted_empty(self):
        masked, err = _mask('""')
        assert err is None
        assert masked == "0"

    # ── backtick strings ─────────────────────────────────────────────────────

    def test_backtick_basic(self):
        masked, err = _mask('`text text`')
        assert err is None
        assert masked == "0"
        assert "text" not in masked

    def test_backtick_with_if_context(self):
        masked, err = _mask('if(length > 10 mm; `hello`; `bye`)')
        assert err is None
        assert "hello" not in masked
        assert "bye" not in masked
        assert "if" in masked
        assert "length" in masked
        assert "mm" in masked

    def test_backtick_unclosed(self):
        masked, err = _mask('`unclosed')
        assert masked is None
        assert "Unclosed" in err

    def test_backtick_multiple(self):
        masked, err = _mask('`foo bar` + `baz`')
        assert err is None
        assert "foo" not in masked
        assert "bar" not in masked
        assert "baz" not in masked
        assert "+" in masked

    def test_backtick_empty(self):
        masked, err = _mask('``')
        assert err is None
        assert masked == "0"

    def test_backslash_not_escape_in_backtick(self):
        # Backtick literals: no escape sequences in v1
        masked, err = _mask(r'`say \n hello`')
        assert err is None
        assert masked == "0"

    # ── mixed / edge cases ───────────────────────────────────────────────────

    def test_empty_input(self):
        masked, err = _mask("")
        assert err is None
        assert masked == ""

    def test_no_literals(self):
        masked, err = _mask("width * 2 + height")
        assert err is None
        assert masked == "width * 2 + height"

    def test_literal_with_numbers_and_symbols(self):
        masked, err = _mask('"hello 123 !@#"')
        assert err is None
        assert masked == "0"

    def test_unclosed_double_in_compound_expression(self):
        masked, err = _mask('x + "oops')
        assert masked is None
        assert "Unclosed" in err

    def test_double_then_backtick(self):
        masked, err = _mask('"alpha" + `beta`')
        assert err is None
        assert "alpha" not in masked
        assert "beta" not in masked
        assert "+" in masked

    def test_replacement_cannot_start_token(self):
        # The replacement char '0' must not be matched as first char of an
        # identifier by EXPRESSION_TOKEN_PATTERN.
        pat = bp.EXPRESSION_TOKEN_PATTERN
        masked, err = _mask('`some words`')
        assert err is None
        matches = pat.findall(masked)
        assert matches == [], f"Unexpected tokens in masked output: {matches}"

    def test_adjacent_literals_no_leak(self):
        # Two back-to-back literals with no space
        masked, err = _mask('`a``b`')
        assert err is None
        assert "a" not in masked
        assert "b" not in masked


# ---------------------------------------------------------------------------
# _validate_expression_response — Fusion-stubbed tests
# ---------------------------------------------------------------------------

class _FakeUnitsManager:
    defaultLengthUnits = "mm"
    def isValidExpression(self, expr, units):
        return True   # accept everything at stub level


class _FakeDesign:
    unitsManager = _FakeUnitsManager()


import contextlib

@contextlib.contextmanager
def _patched_validate(param_names=()):
    orig_design = bp._design
    orig_collect = bp._collect_all_parameter_names
    bp._design = lambda: _FakeDesign()
    bp._collect_all_parameter_names = lambda: list(param_names)
    try:
        yield lambda expr, cur="", units="mm": bp._validate_expression_response(expr, cur, units)
    finally:
        bp._design = orig_design
        bp._collect_all_parameter_names = orig_collect


class TestValidateExpressionLiterals:

    def test_backtick_text_literal_ok(self):
        with _patched_validate() as validate:
            result = validate('`text text`')
        assert result["ok"] is True, result.get("message")

    def test_double_quoted_literal_ok(self):
        with _patched_validate() as validate:
            result = validate('"text text"')
        assert result["ok"] is True, result.get("message")

    def test_if_with_backtick_branches_ok(self):
        with _patched_validate(("width",)) as validate:
            result = validate('if(width > 10 mm; `hello`; `bye`)')
        assert result["ok"] is True, result.get("message")

    def test_if_with_double_quoted_branches_ok(self):
        with _patched_validate(("width",)) as validate:
            result = validate('if(width > 10 mm; "hello"; "bye")')
        assert result["ok"] is True, result.get("message")

    def test_unclosed_backtick_error(self):
        with _patched_validate() as validate:
            result = validate('`unclosed')
        assert result["ok"] is False
        assert "Unclosed" in result["message"]
        assert result.get("isIncomplete") is False

    def test_unclosed_double_quote_error(self):
        with _patched_validate() as validate:
            result = validate('"unclosed')
        assert result["ok"] is False
        assert "Unclosed" in result["message"]

    def test_normal_numeric_expression_unchanged(self):
        with _patched_validate(("width", "height")) as validate:
            result = validate("width * 2 + height")
        assert result["ok"] is True, result.get("message")

    def test_empty_expression_required_error(self):
        with _patched_validate() as validate:
            result = validate("")
        assert result["ok"] is False
        assert "required" in result["message"].lower()

    def test_self_reference_still_caught(self):
        with _patched_validate(("width", "height")) as validate:
            result = validate("width * 2", cur="width")
        assert result["ok"] is False
        assert "currently being edited" in result["message"]

    def test_literal_containing_known_param_name_ok(self):
        # "width" inside a literal must not trigger self-reference error
        with _patched_validate(("width",)) as validate:
            result = validate('`width`', cur="width")
        assert result["ok"] is True, result.get("message")

    def test_literal_plus_real_param_ok(self):
        with _patched_validate(("depth",)) as validate:
            result = validate('`label` + depth')
        assert result["ok"] is True, result.get("message")
