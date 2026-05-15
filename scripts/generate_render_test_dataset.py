#!/usr/bin/env python3
"""Generate deterministic local mock datasets for FE render testing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_JSON_PATH = REPO_ROOT / "tests" / "fixtures" / "render_test_datasets.json"
MOCK_HELPER_PATH = REPO_ROOT / "BetterParameters" / "dev" / "mock_bridge_fixtures.js"

API_VERSION = 1
DEFAULT_TABLE_COLUMNS = {
    "parameter": 140,
    "name": 180,
    "unit": 80,
    "expression": 220,
    "value": 120,
}
DEFAULT_TABLE_ORDER = ["parameter", "name", "unit", "expression", "value", "comment", "revert"]
DEFAULT_UNIT_CATEGORY_STATE = {
    "Length": True,
    "Angle": True,
    "Area": False,
    "Volume": False,
    "Mass": False,
    "Time": False,
    "Density": False,
    "Force": False,
    "Pressure": False,
    "Energy": False,
    "Power": False,
    "Velocity": False,
}


@dataclass(frozen=True)
class FixtureSpec:
    mode: str
    row_count: int
    group_names: tuple[str, ...]
    document_name: str


FIXTURE_SPECS = (
    FixtureSpec(
        mode="render-smoke",
        row_count=8,
        group_names=("Dimensions", "Motion", "Optics"),
        document_name="Render Smoke Fixture",
    ),
    FixtureSpec(
        mode="render-small",
        row_count=24,
        group_names=("Dimensions", "Motion", "Optics", "Manufacturing"),
        document_name="Render Small Fixture",
    ),
    FixtureSpec(
        mode="render-large",
        row_count=180,
        group_names=("Dimensions", "Motion", "Optics", "Manufacturing", "Thermals", "Electrical"),
        document_name="Render Large Fixture",
    ),
)


def _group_id(group_name: str) -> str:
    return f"u:{group_name.lower()}"


def _expression_for_index(index: int) -> str:
    mod = index % 6
    if mod == 0:
        return f"{12 + index} mm"
    if mod == 1:
        return f"{25 + (index * 0.5):.1f} deg"
    if mod == 2:
        return f"{3 + index} cm"
    if mod == 3:
        return f"{index + 2}"
    if mod == 4:
        return f"{4 + index} mm"
    return f"{8 + index} in"


def _unit_for_expression(index: int) -> str:
    mod = index % 6
    if mod in (0, 2, 4):
        return "mm"
    if mod == 1:
        return "deg"
    if mod == 3:
        return ""
    return "in"


def _value_preview(index: int, expression: str, unit: str) -> str:
    if unit == "deg":
        return f"{25 + (index * 0.5):.1f} deg"
    if unit == "":
        return f"{index + 2}"
    value = 10 + (index * 1.125)
    compact = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{compact} {unit}".strip()


def _comment_for_index(index: int, group_name: str) -> str:
    base = f"{group_name} fixture row {index + 1}"
    if index % 9 == 0:
        return f"{base} with extended annotation for clipping and wrap coverage."
    if index % 5 == 0:
        return f"{base} favorite candidate."
    return base


def _parameter_name(index: int, group_name: str) -> str:
    token = group_name.upper().replace(" ", "_")
    return f"{token}_Fixture_{index + 1:03d}"


def _parameter_record(index: int, group_name: str) -> dict[str, object]:
    expression = _expression_for_index(index)
    unit = _unit_for_expression(index)
    value_preview = _value_preview(index, expression, unit)
    prev_expression = "" if index % 4 else _expression_for_index(max(0, index - 1))
    prev_value = "" if index % 4 else _value_preview(max(0, index - 1), prev_expression, unit)
    name = _parameter_name(index, group_name)
    return {
        "key": f"fixture::{name.lower()}",
        "name": name,
        "expression": expression,
        "comment": _comment_for_index(index, group_name),
        "unit": unit,
        "valuePreview": value_preview,
        "isFavorite": index % 7 == 0,
        "group": group_name,
        "previousExpression": prev_expression,
        "previousValue": prev_value,
        "isUserParameter": True,
        "parameterKind": "User Parameter",
        "createdBy": "",
    }


def _settings_payload() -> dict[str, object]:
    return {
        "theme": "light",
        "rememberUnit": False,
        "lastUnit": "",
        "parameterTableColumns": dict(DEFAULT_TABLE_COLUMNS),
        "parameterTableColumnOrder": list(DEFAULT_TABLE_ORDER),
        "unitCategoryState": dict(DEFAULT_UNIT_CATEGORY_STATE),
        "customUnits": [],
        "showRevertButtons": True,
        "alwaysShowRowDragHandle": True,
        "showCommentColumn": True,
        "ultralightNarrowUi": True,
        "showTextTunerSidebar": False,
        "hideGroups": False,
        "autoFitColumns": False,
        "pinnedUnits": [],
        "packageConflictPolicy": "skip",
        "packageImportOptions": {
            "applyExpressionsUnits": True,
            "applyComments": True,
            "applyGroups": True,
            "applyFavorites": True,
            "applyOrder": True,
        },
        "packageExportOptions": {
            "includeFavorites": True,
            "includeGroups": True,
            "includeComments": True,
            "includeOrder": True,
        },
        "computeMode": "manual",
        "autoCheckUpdates": False,
        "autoOpenOnStart": False,
    }


def _state_for_spec(spec: FixtureSpec) -> dict[str, object]:
    parameters = [
        _parameter_record(index, spec.group_names[index % len(spec.group_names)])
        for index in range(spec.row_count)
    ]
    groups = list(spec.group_names)
    return {
        "apiVersion": API_VERSION,
        "parameters": parameters,
        "groups": groups,
        "groupUi": {
            "order": [_group_id(group_name) for group_name in groups],
            "collapsed": {_group_id(group_name): False for group_name in groups},
        },
        "parameterNames": [str(item["name"]) for item in parameters],
        "settings": _settings_payload(),
        "document": {
            "id": f"fixture-{spec.mode}",
            "name": spec.document_name,
        },
        "documentDefaults": {"unit": "mm"},
        "textTunerState": {},
        "fusionTheme": "light",
        "updateInfo": {
            "checkedAt": "",
            "currentVersion": "0.0.0-fixture",
            "latestVersion": "0.0.0-fixture",
            "hasUpdate": False,
            "autoCheckUpdates": False,
        },
    }


def _fixture_bundle() -> dict[str, object]:
    fixtures = {}
    for spec in FIXTURE_SPECS:
        fixtures[spec.mode] = {
            "meta": {
                "mode": spec.mode,
                "rowCount": spec.row_count,
                "groupCount": len(spec.group_names),
                "documentName": spec.document_name,
            },
            "state": _state_for_spec(spec),
        }
    return {
        "generatedAt": "deterministic",
        "defaultMode": FIXTURE_SPECS[0].mode,
        "fixtures": fixtures,
    }


def _mock_helper_source(bundle: dict[str, object]) -> str:
    fixture_json = json.dumps(bundle, indent=2, sort_keys=True)
    return f"""// Generated by scripts/generate_render_test_dataset.py
(function () {{
  var bundle = {fixture_json};
  var fixtures = bundle.fixtures || {{}};
  var defaultMode = String(bundle.defaultMode || "render-smoke").trim().toLowerCase() || "render-smoke";
  var runtimeStateByMode = Object.create(null);

  function clone(value) {{
    return JSON.parse(JSON.stringify(value));
  }}

  function normalizeMode(raw) {{
    var mode = String(raw || "").trim().toLowerCase();
    return mode && Object.prototype.hasOwnProperty.call(fixtures, mode) ? mode : defaultMode;
  }}

  function getFixture(mode) {{
    return fixtures[normalizeMode(mode)] || fixtures[defaultMode];
  }}

  function getRuntimeState(mode) {{
    var key = normalizeMode(mode);
    if (!runtimeStateByMode[key]) {{
      runtimeStateByMode[key] = clone((getFixture(key) || {{}}).state || {{}});
    }}
    return runtimeStateByMode[key];
  }}

  function parsePayload(payloadJson) {{
    if (!payloadJson) return {{}};
    if (typeof payloadJson === "object") return payloadJson;
    try {{
      return JSON.parse(payloadJson);
    }} catch (_error) {{
      return {{}};
    }}
  }}

  function okState(state, extra) {{
    var base = {{ ok: true, message: "", state: clone(state) }};
    if (extra && typeof extra === "object") {{
      Object.keys(extra).forEach(function (key) {{
        base[key] = extra[key];
      }});
    }}
    return base;
  }}

  function okReadOnly(extra) {{
    var base = {{ ok: true, message: "", state: null }};
    if (extra && typeof extra === "object") {{
      Object.keys(extra).forEach(function (key) {{
        base[key] = extra[key];
      }});
    }}
    return base;
  }}

  function findParameter(state, payload) {{
    var parameters = Array.isArray(state.parameters) ? state.parameters : [];
    var key = String(payload.key || "").trim();
    var name = String(payload.name || "").trim();
    for (var i = 0; i < parameters.length; i += 1) {{
      var item = parameters[i];
      if (key && String(item.key || "").trim() === key) return item;
      if (name && String(item.name || "").trim() === name) return item;
    }}
    return null;
  }}

  function applySettingsPatch(state, patch) {{
    if (!patch || typeof patch !== "object") return;
    if (!state.settings || typeof state.settings !== "object") {{
      state.settings = {{}};
    }}
    Object.keys(patch).forEach(function (key) {{
      state.settings[key] = patch[key];
    }});
  }}

  function validateName(name) {{
    var value = String(name || "");
    if (!value.trim()) return "Name is required.";
    if (/^\\d/.test(value)) return "Name cannot start with a number.";
    if (/\\s/.test(value)) return "Name cannot contain spaces or other whitespace.";
    if (!/^[A-Za-z_\"$°µ][A-Za-z0-9_\"$°µ]*$/.test(value)) {{
      return 'Use letters, digits, and only these symbols: _, ", $, °, µ. The name must not start with a digit.';
    }}
    return "";
  }}

  function previewExpression(payload) {{
    var expression = String(payload.expression || "").trim();
    if (!expression) {{
      return {{ ok: false, message: "Expression is required.", state: null }};
    }}
    return okReadOnly({{
      valuePreview: expression,
      expression: expression
    }});
  }}

  window.__BP_MOCK_FIXTURE_HELPER = {{
    bundle: bundle,
    resolve: function (context) {{
      var mode = normalizeMode(context && context.fixtureMode);
      var fixture = getFixture(mode);
      var runtimeState = getRuntimeState(mode);
      var action = String((context && context.action) || "");
      var payload = parsePayload(context && context.payloadJson);
      var actionMap = (context && context.actionMap) || {{}};

      if (action === actionMap.READY || action === actionMap.REFRESH) {{
        return okState(runtimeState);
      }}

      if (action === actionMap.SAVE_SETTINGS) {{
        applySettingsPatch(runtimeState, payload);
        return okState(runtimeState);
      }}

      if (action === actionMap.CHECK_FOR_UPDATES) {{
        runtimeState.updateInfo = {{
          checkedAt: "fixture",
          currentVersion: "0.0.0-fixture",
          latestVersion: "0.0.0-fixture",
          hasUpdate: false,
          autoCheckUpdates: false
        }};
        return okState(runtimeState);
      }}

      if (action === actionMap.GET_MODEL_PARAMETERS) {{
        return okReadOnly({{
          rows: [],
          totalCount: 0,
          offset: 0,
          limit: Number(payload.limit || 200),
          hasMore: false
        }});
      }}

      if (action === actionMap.GET_TEXT_TUNER_STATE) {{
        return okReadOnly({{ values: clone(runtimeState.textTunerState || {{}}) }});
      }}

      if (action === actionMap.VALIDATE_PARAMETER_NAME) {{
        var nameError = validateName(payload.name);
        return nameError ? {{ ok: false, message: nameError, state: null }} : okReadOnly();
      }}

      if (action === actionMap.VALIDATE_EXPRESSION) {{
        var expr = String(payload.expression || "").trim();
        return expr ? okReadOnly() : {{ ok: false, message: "Expression is required.", state: null }};
      }}

      if (action === actionMap.PREVIEW_EXPRESSION) {{
        return previewExpression(payload);
      }}

      if (action === actionMap.REVERT_PARAMETER) {{
        var target = findParameter(runtimeState, payload);
        if (!target) {{
          return {{ ok: false, message: "Parameter not found.", state: null }};
        }}
        target.expression = String(target.previousExpression || target.expression || "");
        target.valuePreview = String(target.previousValue || target.valuePreview || "");
        return okState(runtimeState);
      }}

      if (action === actionMap.BATCH_UPDATE_PARAMETERS) {{
        var updates = Array.isArray(payload.updates) ? payload.updates : [];
        for (var i = 0; i < updates.length; i += 1) {{
          var update = updates[i] || {{}};
          var param = findParameter(runtimeState, update);
          if (!param) continue;
          if (Object.prototype.hasOwnProperty.call(update, "name")) param.name = String(update.name || param.name || "");
          if (Object.prototype.hasOwnProperty.call(update, "expression")) {{
            param.previousExpression = String(param.expression || "");
            param.previousValue = String(param.valuePreview || "");
            param.expression = String(update.expression || "");
            param.valuePreview = String(update.expression || "");
          }}
          if (Object.prototype.hasOwnProperty.call(update, "comment")) param.comment = String(update.comment || "");
        }}
        runtimeState.parameterNames = (runtimeState.parameters || []).map(function (item) {{ return String(item.name || ""); }});
        return okState(runtimeState, {{ failedRows: [] }});
      }}

      if (action === actionMap.RENAME_PARAMETER) {{
        var renameTarget = findParameter(runtimeState, payload);
        var nextName = String(payload.newName || "").trim();
        var renameError = validateName(nextName);
        if (!renameTarget) return {{ ok: false, message: "Parameter not found.", state: null }};
        if (renameError) return {{ ok: false, message: renameError, state: null }};
        renameTarget.name = nextName;
        runtimeState.parameterNames = (runtimeState.parameters || []).map(function (item) {{ return String(item.name || ""); }});
        return okState(runtimeState);
      }}

      if (action === actionMap.RUN_SELF_TEST_SUITE) {{
        return okReadOnly({{
          totalCount: 1,
          passedCount: 1,
          failedCount: 0,
          results: [{{ name: "mock.render.fixture", passed: true, failures: [] }}]
        }});
      }}

      if (fixture && fixture.state && action && context && Array.isArray(context.mutatingActions) && context.mutatingActions.indexOf(action) >= 0) {{
        return okState(runtimeState);
      }}

      return null;
    }}
  }};
}}());
"""


def main() -> int:
    bundle = _fixture_bundle()
    FIXTURE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    MOCK_HELPER_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_JSON_PATH.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MOCK_HELPER_PATH.write_text(_mock_helper_source(bundle), encoding="utf-8")
    print(f"Wrote {FIXTURE_JSON_PATH}")
    print(f"Wrote {MOCK_HELPER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
