"""
test_contract_info.py — verify _get_backend_contract_info structure and values.
"""
import pytest
import BetterParameters as BP


def get_info():
    return BP._get_backend_contract_info()


# ---------------------------------------------------------------------------
# Required keys present
# ---------------------------------------------------------------------------

def test_info_has_contract_version():
    assert "contractVersion" in get_info()


def test_info_has_bpmeta_schema_version():
    assert "bpmetaSchemaVersion" in get_info()


def test_info_has_metadata_schema_version():
    assert "metadataSchemaVersion" in get_info()


def test_info_has_actions():
    assert "actions" in get_info()


def test_info_actions_has_read_only():
    assert "readOnly" in get_info()["actions"]


def test_info_actions_has_mutating():
    assert "mutating" in get_info()["actions"]


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

def test_contract_version_is_string():
    assert isinstance(get_info()["contractVersion"], str)


def test_contract_version_non_empty():
    assert len(get_info()["contractVersion"]) > 0


def test_bpmeta_schema_version_is_int():
    assert isinstance(get_info()["bpmetaSchemaVersion"], int)


def test_bpmeta_schema_version_positive():
    assert get_info()["bpmetaSchemaVersion"] >= 1


def test_metadata_schema_version_is_int():
    assert isinstance(get_info()["metadataSchemaVersion"], int)


def test_read_only_is_list():
    assert isinstance(get_info()["actions"]["readOnly"], list)


def test_mutating_is_list():
    assert isinstance(get_info()["actions"]["mutating"], list)


# ---------------------------------------------------------------------------
# Content checks
# ---------------------------------------------------------------------------

def test_read_only_contains_known_actions():
    ro = get_info()["actions"]["readOnly"]
    assert "getBackendContractInfo" in ro
    assert "getParameterDependencyGraph" in ro
    assert "runSelfTestSuite" in ro
    assert "previewImportParametersFromDataPanel" in ro


def test_mutating_contains_known_actions():
    mut = get_info()["actions"]["mutating"]
    assert "seedTestParameters" in mut
    assert "resetTestState" in mut
    assert "importParametersPackage" in mut
    assert "importParametersFromDataPanel" in mut
    assert "retryImportParametersFromDataPanel" in mut


def test_no_overlap_between_read_only_and_mutating():
    ro = set(get_info()["actions"]["readOnly"])
    mut = set(get_info()["actions"]["mutating"])
    assert ro & mut == set()


def test_contract_version_matches_module_constant():
    assert get_info()["contractVersion"] == BP.CONTRACT_VERSION


def test_bpmeta_schema_version_matches_module_constant():
    assert get_info()["bpmetaSchemaVersion"] == BP.BPMETA_SCHEMA_VERSION
