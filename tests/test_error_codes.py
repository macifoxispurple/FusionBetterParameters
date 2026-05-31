"""
test_error_codes.py — verify stable error code constants and BPError hierarchy.
"""
import pytest
import BetterParameters as BP


# ---------------------------------------------------------------------------
# Error code constants exist and are non-empty strings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("attr", [
    "ERROR_VALIDATION",
    "ERROR_CONFLICT",
    "ERROR_NOT_FOUND",
    "ERROR_IO",
    "ERROR_DIALOG_CANCELLED",
    "ERROR_TRANSPORT",
    "ERROR_CONTRACT",
    "ERROR_NO_DESIGN",
    "ERROR_UNKNOWN",
])
def test_error_constant_exists_and_is_string(attr):
    value = getattr(BP, attr)
    assert isinstance(value, str)
    assert len(value) > 0


# ---------------------------------------------------------------------------
# BPError carries bp_code attribute
# ---------------------------------------------------------------------------

def test_bperror_default_code():
    exc = BP.BPError("something went wrong")
    assert exc.bp_code == BP.ERROR_UNKNOWN


def test_bperror_explicit_code():
    exc = BP.BPError("oops", BP.ERROR_IO)
    assert exc.bp_code == BP.ERROR_IO


def test_bperror_is_exception():
    with pytest.raises(BP.BPError):
        raise BP.BPError("test")


# ---------------------------------------------------------------------------
# Subclass codes are correct
# ---------------------------------------------------------------------------

def test_bpvalidation_error_code():
    exc = BP.BPValidationError("bad input")
    assert exc.bp_code == BP.ERROR_VALIDATION


def test_bpconflict_error_code():
    exc = BP.BPConflictError("already exists")
    assert exc.bp_code == BP.ERROR_CONFLICT


def test_bpnotfound_error_code():
    exc = BP.BPNotFoundError("not found")
    assert exc.bp_code == BP.ERROR_NOT_FOUND


def test_bpio_error_code():
    exc = BP.BPIOError("disk error")
    assert exc.bp_code == BP.ERROR_IO


def test_bpnodesign_error_code():
    exc = BP.BPNoDesignError()
    assert exc.bp_code == BP.ERROR_NO_DESIGN


# ---------------------------------------------------------------------------
# All subclasses inherit from BPError
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls_name", [
    "BPValidationError",
    "BPConflictError",
    "BPNotFoundError",
    "BPIOError",
    "BPNoDesignError",
])
def test_subclass_inherits_bperror(cls_name):
    cls = getattr(BP, cls_name)
    assert issubclass(cls, BP.BPError)


# ---------------------------------------------------------------------------
# Action lists contain expected entries
# ---------------------------------------------------------------------------

def test_read_only_actions_list():
    assert "getBackendContractInfo" in BP._READ_ONLY_ACTIONS
    assert "getParameterDependencyGraph" in BP._READ_ONLY_ACTIONS
    assert "runSelfTestSuite" in BP._READ_ONLY_ACTIONS
    assert "previewImportParametersFromDataPanel" in BP._READ_ONLY_ACTIONS


def test_mutating_actions_list():
    assert "seedTestParameters" in BP._MUTATING_ACTIONS
    assert "resetTestState" in BP._MUTATING_ACTIONS
    assert "importParametersFromDataPanel" in BP._MUTATING_ACTIONS
    assert "retryImportParametersFromDataPanel" in BP._MUTATING_ACTIONS


def test_no_overlap_between_action_lists():
    overlap = set(BP._READ_ONLY_ACTIONS) & set(BP._MUTATING_ACTIONS)
    assert overlap == set(), f"Actions in both lists: {overlap}"
