"""
test_bpmeta_parse.py — tests for _parse_bpmeta_package.

Pure function: no design, no Fusion API, no file I/O.
"""
import json
import pytest
import BetterParameters as bp
from helpers import make_package_json, make_param_record, BPMETA_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Valid packages
# ---------------------------------------------------------------------------

def test_valid_minimal_package():
    raw = make_package_json([])
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is not None
    assert err == ""
    assert pkg["schemaVersion"] == BPMETA_SCHEMA_VERSION
    assert pkg["parameters"] == []


def test_valid_package_with_parameters():
    records = [
        make_param_record("width", "100 mm", "mm", comment="Overall width", group="Dims", isFavorite=True),
        make_param_record("height", "50 mm", "mm"),
    ]
    raw = make_package_json(records)
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is not None
    assert err == ""
    assert len(pkg["parameters"]) == 2
    assert pkg["parameters"][0]["name"] == "width"


def test_valid_package_unknown_extra_fields_tolerated():
    pkg_dict = {
        "schemaVersion": BPMETA_SCHEMA_VERSION,
        "exportedAt": "2026-01-01T00:00:00Z",
        "futureField": "ignored",
        "parameters": [],
    }
    pkg, err = bp._parse_bpmeta_package(json.dumps(pkg_dict))
    assert pkg is not None
    assert err == ""


# ---------------------------------------------------------------------------
# JSON-level failures
# ---------------------------------------------------------------------------

def test_invalid_json():
    pkg, err = bp._parse_bpmeta_package("not json {{{")
    assert pkg is None
    assert "JSON parse error" in err


def test_empty_string():
    pkg, err = bp._parse_bpmeta_package("")
    assert pkg is None
    assert err != ""


def test_json_array_not_object():
    pkg, err = bp._parse_bpmeta_package(json.dumps([1, 2, 3]))
    assert pkg is None
    assert "expected a JSON object" in err


def test_json_null():
    pkg, err = bp._parse_bpmeta_package("null")
    assert pkg is None
    assert err != ""


# ---------------------------------------------------------------------------
# schemaVersion failures
# ---------------------------------------------------------------------------

def test_missing_schema_version():
    raw = json.dumps({"parameters": []})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert "schemaVersion" in err


def test_schema_version_zero():
    raw = json.dumps({"schemaVersion": 0, "parameters": []})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert err != ""


def test_schema_version_negative():
    raw = json.dumps({"schemaVersion": -1, "parameters": []})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert err != ""


def test_schema_version_too_new():
    raw = json.dumps({"schemaVersion": BPMETA_SCHEMA_VERSION + 1, "parameters": []})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert "newer than supported" in err
    assert str(BPMETA_SCHEMA_VERSION + 1) in err


def test_schema_version_string_type():
    raw = json.dumps({"schemaVersion": "1", "parameters": []})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert err != ""


def test_schema_version_float():
    raw = json.dumps({"schemaVersion": 1.0, "parameters": []})
    pkg, err = bp._parse_bpmeta_package(raw)
    # 1.0 is not isinstance int in Python (float != int)
    assert pkg is None
    assert err != ""


def test_schema_version_current_accepted():
    raw = json.dumps({"schemaVersion": BPMETA_SCHEMA_VERSION, "parameters": []})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is not None
    assert err == ""


# ---------------------------------------------------------------------------
# parameters field failures
# ---------------------------------------------------------------------------

def test_parameters_missing():
    raw = json.dumps({"schemaVersion": BPMETA_SCHEMA_VERSION})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert '"parameters"' in err


def test_parameters_is_object_not_array():
    raw = json.dumps({"schemaVersion": BPMETA_SCHEMA_VERSION, "parameters": {}})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert "array" in err


def test_parameters_is_null():
    raw = json.dumps({"schemaVersion": BPMETA_SCHEMA_VERSION, "parameters": None})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert err != ""


def test_parameters_is_string():
    raw = json.dumps({"schemaVersion": BPMETA_SCHEMA_VERSION, "parameters": "nope"})
    pkg, err = bp._parse_bpmeta_package(raw)
    assert pkg is None
    assert err != ""
