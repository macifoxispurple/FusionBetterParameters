"""
helpers.py — shared mock factories for BetterParameters offline tests.
"""
import json
from unittest.mock import MagicMock

BPMETA_SCHEMA_VERSION = 1  # keep in sync with BetterParameters.BPMETA_SCHEMA_VERSION


def make_mock_param(name="width", expression="10 mm", unit="mm", comment="", is_favorite=False):
    """Return a MagicMock that looks like a Fusion UserParameter."""
    p = MagicMock()
    p.name = name
    p.expression = expression
    p.unit = unit
    p.comment = comment
    p.isFavorite = is_favorite
    return p


def make_mock_design(existing_params=None):
    """Return a MagicMock Fusion Design with optional existing user parameters.

    existing_params: list of dicts with keys: name, expression, unit, comment, isFavorite.
    All are accessible via design.userParameters.itemByName(name) and
    design.allParameters.itemByName(name).
    """
    existing_params = existing_params or []
    param_map = {}
    for spec in existing_params:
        p = make_mock_param(
            name=spec.get("name", ""),
            expression=spec.get("expression", "10 mm"),
            unit=spec.get("unit", "mm"),
            comment=spec.get("comment", ""),
            is_favorite=spec.get("isFavorite", False),
        )
        param_map[spec["name"]] = p

    param_list = list(param_map.values())

    def item_by_name(name):
        return param_map.get(name)

    def all_params_item(index):
        if 0 <= index < len(param_list):
            return param_list[index]
        return None

    design = MagicMock()
    design.userParameters.itemByName.side_effect = item_by_name
    design.allParameters.itemByName.side_effect = item_by_name
    # Support count + item(index) iteration used by _collect_all_parameter_names.
    design.allParameters.count = len(param_list)
    design.allParameters.item.side_effect = all_params_item
    design.unitsManager.defaultLengthUnits = "mm"
    # isValidExpression defaults to True; override per-test as needed.
    design.unitsManager.isValidExpression.return_value = True
    return design


def make_package(parameters, schema_version=BPMETA_SCHEMA_VERSION, exported_at=None, source_doc=None):
    """Build a minimal valid bpmeta package dict."""
    pkg = {
        "schemaVersion": schema_version,
        "exportedAt": exported_at or "2026-01-01T00:00:00Z",
        "sourceDocument": source_doc or {"name": "TestDoc"},
        "parameters": parameters,
    }
    return pkg


def make_package_json(parameters, **kwargs):
    """Build a bpmeta package and return it as a JSON string."""
    return json.dumps(make_package(parameters, **kwargs))


def make_param_record(name="width", expression="10 mm", unit="mm", **extra):
    """Return a minimal valid package parameter record."""
    record = {"name": name, "expression": expression, "unit": unit}
    record.update(extra)
    return record
