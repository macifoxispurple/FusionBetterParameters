import json
import importlib
import importlib.util
import os
import re
import shutil
import sys
import time
import traceback
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import adsk.core
import adsk.fusion

ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDIN_DIR not in sys.path:
    sys.path.insert(0, ADDIN_DIR)

import update_state as _update_state
_update_state = importlib.reload(_update_state)
from update_state import (
    STATE_APPLIED, STATE_FAILED, STATE_STAGED,
    applied_update_state, clear_update_state, fail_update_state,
    normalize_update_state, read_update_state, stage_update_state,
    startup_preference_after_apply, write_update_state,
)

CMD_ID = "betterParametersShowPalette"
CMD_NAME = "Better Parameters"
CMD_DESCRIPTION = "Show a non-blocking palette for Fusion user parameters."
WORKSPACE_ID = "FusionSolidEnvironment"
TAB_ID = "ToolsTab"
PANEL_ID = "BetterParametersPanel"
PANEL_NAME = "Better Parameters"
PALETTE_ID = "betterParametersPalette"
PALETTE_NAME = "Better Parameters"
PALETTE_FILE = "palette.html"
COMMAND_RESOURCES = "./Resources/BetterParameters"
SETTINGS_FILE = "settings.json"
DEFAULT_PALETTE_WIDTH = 520
DEFAULT_PALETTE_HEIGHT = 640
EXPRESSION_TOKEN_PATTERN = re.compile(r'[A-Za-z_"\$Â°Âµ][A-Za-z0-9_"\$Â°Âµ]*')
ALLOWED_EXPRESSION_IDENTIFIERS = {
    "PI", "E", "Gravity", "SpeedOfLight",
    "if", "and", "or", "not",
    "cos", "sin", "tan", "acos", "acosh", "asin", "asinh", "atan", "atanh",
    "cosh", "sinh", "tanh", "sqrt", "sign", "exp", "floor", "ceil", "round",
    "abs", "max", "min", "ln", "log", "pow", "random",
}
PARAMETER_NAME_PATTERN = re.compile(r'^[A-Za-z_"\$°µ][A-Za-z0-9_"\$°µ]*$')

MANIFEST_PATH = os.path.join(ADDIN_DIR, "BetterParameters.manifest")
LATEST_RELEASE_API_URL = "https://api.github.com/repos/macifoxispurple/FusionBetterParameters/releases/latest"
LATEST_RELEASE_PAGE_URL = "https://github.com/macifoxispurple/FusionBetterParameters/releases/latest"
UPDATE_CACHE_MAX_AGE_SECONDS = 5 * 60
PENDING_UPDATE_DIR = os.path.join(ADDIN_DIR, "_pending_update")
PENDING_UPDATE_INFO_PATH = os.path.join(PENDING_UPDATE_DIR, "update.json")
UPDATE_HELPER_PATH = os.path.join(ADDIN_DIR, "update_helper.py")
UPDATE_STATE_PATH = os.path.join(ADDIN_DIR, "update_state.json")

DEFAULT_SETTINGS = {
    "theme": "light",
    "rememberUnit": False,
    "lastUnit": "",
    "paletteSize": {
        "width": DEFAULT_PALETTE_WIDTH,
        "height": DEFAULT_PALETTE_HEIGHT,
    },
    "parameterTableColumns": {
        "name": 21,
        "expression": 27,
        "preview": 16,
        "comment": 24,
        "actions": 12,
    },
    "unitCategoryState": {
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
    },
    "autoCheckUpdates": True,
    "updateCheck": {},
}
TARGET_PANEL_IDS = [
    PANEL_ID,
    "SolidModifyPanel",
    "SurfaceModifyPanel",
    "MeshModifyPanel",
    "SheetMetalModifyPanel",
    "PlasticModifyPanel",
]


handlers = []
app = adsk.core.Application.cast(None)
ui = adsk.core.UserInterface.cast(None)
command_handler_registered = False
_updated_runtime_module = None


def run(context):
    global app, ui

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        update_result = _apply_pending_update_if_needed()
        if update_result and update_result.get("status") == "applied":
            _launch_updated_addin_from_disk(context)
            return
        if update_result and update_result.get("status") == "failed":
            if ui:
                ui.messageBox(
                    "Better Parameters could not apply the staged update:\n{}".format(update_result["error"]),
                    CMD_NAME,
                )

        _register_command()
        _register_application_events()
    except Exception:
        _message_box(f"Add-in start failed:\n{traceback.format_exc()}")


def stop(_context):
    try:
        palette = _palette()
        if palette:
            palette.deleteMe()
    except Exception:
        _message_box(f"Add-in stop failed:\n{traceback.format_exc()}")


def _register_command():
    global command_handler_registered

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if not cmd_def:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            CMD_ID,
            CMD_NAME,
            CMD_DESCRIPTION,
            COMMAND_RESOURCES,
        )

    if not command_handler_registered:
        on_command_created = ShowPaletteCommandCreatedHandler()
        cmd_def.commandCreated.add(on_command_created)
        handlers.append(on_command_created)
        command_handler_registered = True

    _ensure_command_controls(cmd_def)


def _register_application_events():
    on_document_activated = DocumentActivatedHandler()
    app.documentActivated.add(on_document_activated)
    handlers.append(on_document_activated)


class ShowPaletteCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            on_execute = ShowPaletteExecuteHandler()
            args.command.execute.add(on_execute)
            handlers.append(on_execute)
        except Exception:
            _message_box(f"Command creation failed:\n{traceback.format_exc()}")


class ShowPaletteExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, _args):
        try:
            palette = _ensure_palette()
            palette.isVisible = True
            _push_parameter_list()
        except Exception:
            _message_box(f"Opening palette failed:\n{traceback.format_exc()}")


class DocumentActivatedHandler(adsk.core.DocumentEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, _args):
        try:
            palette = _palette()
            if palette and palette.isVisible:
                _send_to_palette("renderState", _current_state_payload())
        except Exception:
            if app:
                app.log(f"Better Parameters documentActivated refresh failed:\n{traceback.format_exc()}")


class PaletteIncomingHandler(adsk.core.HTMLEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        html_args = adsk.core.HTMLEventArgs.cast(args)
        try:
            if not html_args:
                return

            data = json.loads(html_args.data) if html_args.data else {}
            result = _handle_palette_action(html_args.action, data)
            html_args.returnData = json.dumps(result)
        except Exception as exc:
            if html_args:
                html_args.returnData = json.dumps(
                    {
                        "ok": False,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )


class PaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, _args):
        try:
            palette = _palette()
            if palette:
                palette.deleteMe()
        except Exception:
            _message_box(f"Palette cleanup failed:\n{traceback.format_exc()}")


def _ensure_palette():
    palette = _palette()
    if palette:
        return palette

    palette = ui.palettes.add(
        PALETTE_ID,
        PALETTE_NAME,
        PALETTE_FILE,
        True,
        True,
        True,
        DEFAULT_PALETTE_WIDTH,
        DEFAULT_PALETTE_HEIGHT,
    )
    palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
    _apply_saved_palette_size(palette)

    on_incoming = PaletteIncomingHandler()
    palette.incomingFromHTML.add(on_incoming)
    handlers.append(on_incoming)

    on_closed = PaletteClosedHandler()
    palette.closed.add(on_closed)
    handlers.append(on_closed)

    return palette


def _palette():
    return ui.palettes.itemById(PALETTE_ID) if ui else None


def _workspace():
    return ui.workspaces.itemById(WORKSPACE_ID) if ui else None


def _panel_by_id(panel_id):
    workspace = _workspace()
    return workspace.toolbarPanels.itemById(panel_id) if workspace else None


def _toolbar_panel():
    return _panel_by_id(PANEL_ID)


def _ensure_toolbar_panel():
    panel = _toolbar_panel()
    if panel:
        return panel

    workspace = _workspace()
    if not workspace:
        raise RuntimeError("Fusion design workspace is unavailable.")

    tools_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if not tools_tab:
        raise RuntimeError("Fusion Utilities tab is unavailable.")

    return tools_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME)


def _ensure_command_controls(cmd_def):
    utility_panel = _ensure_toolbar_panel()
    if utility_panel and not utility_panel.controls.itemById(CMD_ID):
        control = utility_panel.controls.addCommand(cmd_def)
        control.isPromotedByDefault = True
        control.isPromoted = True

    for panel_id in TARGET_PANEL_IDS:
        if panel_id == PANEL_ID:
            continue

        panel = _panel_by_id(panel_id)
        if panel and not panel.controls.itemById(CMD_ID):
            panel.controls.addCommand(cmd_def)


def _handle_palette_action(action, data):
    if action == "ready":
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "refresh":
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "updateParameter":
        _update_parameter(data)
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "createParameter":
        _create_parameter(data)
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "saveSettings":
        settings = _save_settings(data)
        payload = _current_state_payload(settings=settings)
        _send_to_palette("renderState", payload)
        return payload

    if action == "validateParameterName":
        return _validate_parameter_name_response(data.get("name", ""))

    if action == "validateExpression":
        return _validate_expression_response(
            data.get("expression", ""),
            data.get("currentParameterName", ""),
            data.get("units", "")
        )

    if action == "getActiveDocumentInfo":
        return {"ok": True, "document": _active_document_info()}

    if action == "checkForUpdates":
        release_info = _latest_release_info(force_refresh=True)
        _save_update_check(release_info)
        return _current_state_payload()

    if action == "downloadAndStageUpdate":
        release_info = _latest_release_info(force_refresh=True, allow_cached_on_error=False)
        _stage_update_payload(release_info)
        return _current_state_payload()

    return {"ok": False, "message": f"Unknown action: {action}"}


def _push_parameter_list():
    _send_to_palette("renderState", _current_state_payload())


def _send_to_palette(action, payload):
    palette = _palette()
    if palette:
        palette.sendInfoToHTML(action, json.dumps(payload))


def _current_state_payload(settings=None):
    active_settings = settings if settings is not None else _load_settings()
    return {
        "ok": True,
        "parameters": _collect_user_parameters(),
        "parameterNames": _collect_all_parameter_names(),
        "settings": active_settings,
        "document": _active_document_info(),
        "documentDefaults": {
            "unit": _default_document_unit(),
        },
        "updateInfo": _build_update_info_payload(),
    }


def _build_update_info_payload():
    current_version = _current_addin_version()
    update_state = _current_update_state()
    settings = _load_settings()
    auto_check = bool(settings.get("autoCheckUpdates", True))

    cached = _normalized_update_check(settings.get("updateCheck") or {})
    latest_version = cached.get("latest_version", "")
    has_update = bool(latest_version and _is_version_newer(latest_version, current_version))

    return {
        "currentVersion": current_version,
        "latestVersion": latest_version,
        "hasUpdate": has_update,
        "latestUrl": cached.get("latest_url") or LATEST_RELEASE_PAGE_URL,
        "autoCheckUpdates": auto_check,
        "updateState": update_state.get("state", "idle"),
        "targetVersion": update_state.get("target_version", ""),
        "error": cached.get("error", ""),
    }


def _design():
    product = app.activeProduct if app else None
    return adsk.fusion.Design.cast(product)


def _collect_user_parameters():
    design = _design()
    if not design:
        return []

    units_manager = design.unitsManager
    results = []
    params = design.userParameters
    for index in range(params.count):
        param = params.item(index)
        if not param:
            continue

        results.append(
            {
                "name": param.name,
                "expression": param.expression,
                "unit": param.unit,
                "comment": param.comment or "",
                "isFavorite": param.isFavorite,
                "valuePreview": _format_parameter_value(param, units_manager),
            }
        )

    return results


def _collect_all_parameter_names():
    design = _design()
    if not design:
        return []

    names = []
    params = design.allParameters
    for index in range(params.count):
        param = params.item(index)
        if not param or not param.name:
            continue
        names.append(param.name)

    return sorted(set(names), key=str.casefold)


def _settings_path():
    return Path(__file__).resolve().with_name(SETTINGS_FILE)


def _load_settings():
    settings = dict(DEFAULT_SETTINGS)
    settings["paletteSize"] = dict(DEFAULT_SETTINGS["paletteSize"])
    settings["parameterTableColumns"] = dict(DEFAULT_SETTINGS["parameterTableColumns"])
    settings["unitCategoryState"] = dict(DEFAULT_SETTINGS["unitCategoryState"])
    settings["updateCheck"] = {}
    settings_path = _settings_path()
    if not settings_path.exists():
        return settings

    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return settings

    if isinstance(loaded, dict):
        if "theme" in loaded:
            settings["theme"] = loaded["theme"]
        if isinstance(loaded.get("rememberUnit"), bool):
            settings["rememberUnit"] = loaded["rememberUnit"]
        if isinstance(loaded.get("lastUnit"), str):
            settings["lastUnit"] = loaded["lastUnit"]
        if isinstance(loaded.get("paletteSize"), dict):
            width = loaded["paletteSize"].get("width")
            height = loaded["paletteSize"].get("height")
            if isinstance(width, int) and width >= 320:
                settings["paletteSize"]["width"] = width
            if isinstance(height, int) and height >= 240:
                settings["paletteSize"]["height"] = height
        if isinstance(loaded.get("parameterTableColumns"), dict):
            for key, default_value in DEFAULT_SETTINGS["parameterTableColumns"].items():
                incoming_value = loaded["parameterTableColumns"].get(key)
                if isinstance(incoming_value, (int, float)) and incoming_value > 0:
                    settings["parameterTableColumns"][key] = float(incoming_value)

        if isinstance(loaded.get("unitCategoryState"), dict):
            for key, default_value in DEFAULT_SETTINGS["unitCategoryState"].items():
                incoming_value = loaded["unitCategoryState"].get(key)
                if isinstance(incoming_value, bool):
                    settings["unitCategoryState"][key] = incoming_value

        if isinstance(loaded.get("autoCheckUpdates"), bool):
            settings["autoCheckUpdates"] = loaded["autoCheckUpdates"]

        if isinstance(loaded.get("updateCheck"), dict):
            settings["updateCheck"] = _normalized_update_check(loaded["updateCheck"])

    if settings.get("theme") not in {"light", "dark"}:
        settings["theme"] = DEFAULT_SETTINGS["theme"]

    return settings


def _save_settings(data):
    settings = _load_settings()

    requested_theme = (data.get("theme") or "").strip().lower()
    if requested_theme:
        if requested_theme not in {"light", "dark"}:
            raise ValueError(f'Unsupported theme "{requested_theme}".')
        settings["theme"] = requested_theme

    if "rememberUnit" in data:
        remember_unit = data.get("rememberUnit")
        if not isinstance(remember_unit, bool):
            raise ValueError('"rememberUnit" must be a boolean.')
        settings["rememberUnit"] = remember_unit

    if "lastUnit" in data:
        last_unit = data.get("lastUnit")
        if not isinstance(last_unit, str):
            raise ValueError('"lastUnit" must be a string.')
        settings["lastUnit"] = last_unit

    palette_size = data.get("paletteSize")
    if palette_size is not None:
        if not isinstance(palette_size, dict):
            raise ValueError('"paletteSize" must be an object.')

        width = palette_size.get("width")
        height = palette_size.get("height")
        if width is not None:
            if not isinstance(width, int) or width < 320:
                raise ValueError('"paletteSize.width" must be an integer greater than or equal to 320.')
            settings["paletteSize"]["width"] = width
        if height is not None:
            if not isinstance(height, int) or height < 240:
                raise ValueError('"paletteSize.height" must be an integer greater than or equal to 240.')
            settings["paletteSize"]["height"] = height

    table_columns = data.get("parameterTableColumns")
    if table_columns is not None:
        if not isinstance(table_columns, dict):
            raise ValueError('"parameterTableColumns" must be an object.')

        normalized = dict(settings["parameterTableColumns"])
        for key in DEFAULT_SETTINGS["parameterTableColumns"]:
            incoming_value = table_columns.get(key)
            if incoming_value is not None:
                if not isinstance(incoming_value, (int, float)) or incoming_value <= 0:
                    raise ValueError(f'"parameterTableColumns.{key}" must be a positive number.')
                normalized[key] = float(incoming_value)

        total = sum(normalized.values())
        if total <= 0:
            raise ValueError('"parameterTableColumns" total must be greater than 0.')

        settings["parameterTableColumns"] = {
            key: round((value / total) * 100, 2) for key, value in normalized.items()
        }

    category_state = data.get("unitCategoryState")
    if category_state is not None:
        if not isinstance(category_state, dict):
            raise ValueError('"unitCategoryState" must be an object.')

        for key, default_value in DEFAULT_SETTINGS["unitCategoryState"].items():
            incoming_value = category_state.get(key)
            if isinstance(incoming_value, bool):
                settings["unitCategoryState"][key] = incoming_value

    if "autoCheckUpdates" in data:
        auto_check = data.get("autoCheckUpdates")
        if not isinstance(auto_check, bool):
            raise ValueError('"autoCheckUpdates" must be a boolean.')
        settings["autoCheckUpdates"] = auto_check

    if "updateCheck" in data:
        settings["updateCheck"] = _normalized_update_check(data["updateCheck"])

    settings_path = _settings_path()
    temp_path = settings_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    temp_path.replace(settings_path)
    return settings


def _format_parameter_value(param, units_manager):
    try:
        if param.unit:
            return units_manager.formatValue(param.value, param.unit, -1, adsk.core.BooleanOptions.DefaultBooleanOption, -1, True)
        return param.textValue
    except Exception:
        return ""


def _default_document_unit():
    design = _design()
    if not design:
        return "mm"

    try:
        default_unit = design.unitsManager.defaultLengthUnits
        return default_unit or "mm"
    except Exception:
        return "mm"


def _active_document_info():
    document = app.activeDocument if app else None
    if not document:
        return {"id": "", "name": ""}

    document_id = ""
    try:
        document_id = document.creationId or ""
    except Exception:
        document_id = ""

    document_name = ""
    try:
        document_name = document.name or ""
    except Exception:
        document_name = ""

    return {"id": document_id, "name": document_name}


def _apply_saved_palette_size(palette):
    settings = _load_settings()
    width = settings["paletteSize"]["width"]
    height = settings["paletteSize"]["height"]
    try:
        palette.width = width
        palette.height = height
    except Exception:
        if app:
            app.log(f"Better Parameters palette size restore failed:\n{traceback.format_exc()}")


def _update_parameter(data):
    design = _require_design()
    name = _required_text(data, "name")
    expression = _required_text(data, "expression")
    comment = data.get("comment", "")

    param = design.userParameters.itemByName(name)
    if not param:
        raise ValueError(f'User parameter "{name}" was not found.')

    param.expression = expression
    param.comment = comment


def _create_parameter(data):
    design = _require_design()
    name = _required_text(data, "name")
    expression = _required_text(data, "expression")
    units = data.get("unit", "").strip()
    comment = data.get("comment", "")

    validation = _validate_parameter_name_response(name)
    if not validation["ok"]:
        raise ValueError(validation["message"])

    expression_validation = _validate_expression_response(expression, name, units)
    if not expression_validation["ok"]:
        raise ValueError(expression_validation["message"])

    unit_value = units or ""
    value_input = adsk.core.ValueInput.createByString(expression)
    created = design.userParameters.add(name, value_input, unit_value, comment)
    if not created:
        raise ValueError("Fusion rejected the new parameter.")


def _validate_parameter_name_response(name):
    trimmed_name = (name or "").strip()
    if not trimmed_name:
        return {"ok": False, "message": "Name is required."}

    if trimmed_name != (name or ""):
        return {"ok": False, "message": "Name cannot start or end with whitespace."}

    if any(char.isspace() for char in trimmed_name):
        return {"ok": False, "message": "Name cannot contain spaces or other whitespace."}

    if not PARAMETER_NAME_PATTERN.match(trimmed_name):
        return {
            "ok": False,
            "message": 'Use letters, digits, and only these symbols: _, ", $, °, µ. The name must not start with a digit.'
        }

    design = _design()
    if design and design.allParameters.itemByName(trimmed_name):
        return {"ok": False, "message": f'A parameter named "{trimmed_name}" already exists in this design.'}

    return {"ok": True, "message": ""}


def _validate_expression_response(expression, current_parameter_name="", units=""):
    text = (expression or "").strip()
    if not text:
        return {"ok": False, "message": "Expression is required."}

    parameter_names = set(_collect_all_parameter_names())
    allowed_identifiers = set(ALLOWED_EXPRESSION_IDENTIFIERS)
    allowed_identifiers.update(_known_unit_identifiers())

    unknown_tokens = []
    for match in EXPRESSION_TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if current_parameter_name and token == current_parameter_name:
            return {
                "ok": False,
                "message": f'Expression cannot reference "{current_parameter_name}" exactly because that is the parameter currently being edited.'
            }
        if token in parameter_names or token in allowed_identifiers:
            continue
        unknown_tokens.append(token)

    if unknown_tokens:
        token = unknown_tokens[0]
        case_hint = _case_sensitive_parameter_hint(token, parameter_names)
        if case_hint:
            return {
                "ok": False,
                "message": f'Unknown parameter name "{token}". Parameter names are case sensitive. Did you mean "{case_hint}"?'
            }
        return {
            "ok": False,
            "message": f'Unknown parameter name "{token}". Parameter names are case sensitive and must match an existing parameter exactly.'
        }

    design = _design()
    if design:
        try:
            validate_units = units or design.unitsManager.defaultLengthUnits or "mm"
            if not design.unitsManager.isValidExpression(text, validate_units):
                return {
                    "ok": False,
                    "message": "Expression syntax is invalid. Use explicit operators between terms; parentheses do not imply multiplication."
                }
        except Exception:
            pass

    return {"ok": True, "message": ""}


def _case_sensitive_parameter_hint(token, parameter_names):
    token_folded = token.casefold()
    for name in parameter_names:
        if name.casefold() == token_folded and name != token:
            return name
    return ""


def _known_unit_identifiers():
    return {
        "mm", "cm", "m", "in", "ft", "deg", "rad",
        "mm^2", "cm^2", "m^2", "in^2", "ft^2",
        "mm^3", "cm^3", "m^3", "in^3", "ft^3", "L",
        "g", "kg", "lbmass", "s", "min", "hour",
        "kg/m^3", "g/cm^3", "N", "lbf", "Pa", "kPa", "MPa", "psi",
        "J", "kJ", "W", "kW", "hp", "mm/s", "cm/s", "m/s", "in/s", "ft/s",
        "Text",
    }


def _require_design():
    design = _design()
    if not design:
        raise RuntimeError("Open a Fusion design before using Better Parameters.")
    return design


def _required_text(data, key):
    value = (data.get(key) or "").strip()
    if not value:
        raise ValueError(f'"{key}" is required.')
    return value


def _message_box(message):
    if ui:
        ui.messageBox(message)


# ── Update helpers ────────────────────────────────────────────────────────────

def _safe_call(fn):
    try:
        return fn()
    except Exception:
        return None


def _current_addin_version():
    try:
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as handle:
            return str(json.load(handle).get('version', '')).strip() or '0.0.0'
    except Exception:
        return '0.0.0'


def _version_parts(version_text):
    text = (version_text or '').strip().lower()
    if text.startswith('v'):
        text = text[1:]
    parts = []
    for part in text.split('.'):
        digits = ''.join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or '0'))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _is_version_newer(candidate_version, current_version):
    return _version_parts(candidate_version) > _version_parts(current_version)


def _normalized_update_check(value):
    if not isinstance(value, dict):
        return {}
    normalized = {}
    if isinstance(value.get('checked_at'), (int, float)):
        normalized['checked_at'] = float(value['checked_at'])
    if isinstance(value.get('latest_version'), str):
        normalized['latest_version'] = value['latest_version'].strip()
    if isinstance(value.get('latest_url'), str):
        normalized['latest_url'] = value['latest_url'].strip()
    if isinstance(value.get('latest_asset_url'), str):
        normalized['latest_asset_url'] = value['latest_asset_url'].strip()
    if isinstance(value.get('latest_asset_name'), str):
        normalized['latest_asset_name'] = value['latest_asset_name'].strip()
    if isinstance(value.get('latest_notes'), str):
        normalized['latest_notes'] = value['latest_notes'].strip()
    if isinstance(value.get('error'), str):
        normalized['error'] = value['error'].strip()
    return normalized


def _save_update_check(update_check):
    path = _settings_path()
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        existing = {}
    existing["updateCheck"] = _normalized_update_check(update_check)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _release_zip_asset(payload):
    assets = payload.get('assets') or []
    zip_assets = [asset for asset in assets if str(asset.get('name', '')).lower().endswith('.zip')]
    for asset in zip_assets:
        name = str(asset.get('name') or '')
        if name.lower().startswith('betterparameters-'):
            return asset
    return zip_assets[0] if zip_assets else {}


def _normalized_release_notes(body_text):
    text = str(body_text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return ''
    lines = [line.rstrip() for line in text.split('\n')]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines).strip()


def _release_notes_html(notes_text):
    import html as _html
    text = _normalized_release_notes(notes_text)
    if not text:
        return ''
    return '<br/>'.join(_html.escape(line) if line.strip() else '' for line in text.split('\n'))


def _fetch_latest_release_info():
    request = urllib.request.Request(
        LATEST_RELEASE_API_URL,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'BetterParameters',
            'Cache-Control': 'no-cache'
        }
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        payload = json.loads(response.read().decode('utf-8'))

    latest_version = str(payload.get('tag_name') or payload.get('name') or '').strip()
    if latest_version.lower().startswith('v'):
        latest_version = latest_version[1:]

    latest_url = str(payload.get('html_url') or LATEST_RELEASE_PAGE_URL).strip() or LATEST_RELEASE_PAGE_URL
    asset = _release_zip_asset(payload)
    latest_asset_url = str(asset.get('browser_download_url') or '').strip()
    latest_asset_name = str(asset.get('name') or '').strip()
    latest_notes = _normalized_release_notes(payload.get('body') or '')
    if not latest_version:
        raise ValueError('GitHub did not return a release version.')

    return {
        'checked_at': time.time(),
        'latest_version': latest_version,
        'latest_url': latest_url,
        'latest_asset_url': latest_asset_url,
        'latest_asset_name': latest_asset_name,
        'latest_notes': latest_notes,
        'error': ''
    }


def _latest_release_info(force_refresh=False, allow_cached_on_error=True):
    settings = _load_settings()
    cached = _normalized_update_check(settings.get('updateCheck') or {})
    checked_at = cached.get('checked_at', 0)
    is_fresh = bool(checked_at and (time.time() - checked_at) < UPDATE_CACHE_MAX_AGE_SECONDS)

    if cached and not force_refresh and is_fresh:
        return cached

    try:
        latest = _fetch_latest_release_info()
        _save_update_check(latest)
        return latest
    except Exception as exc:
        if cached and allow_cached_on_error:
            cached['error'] = str(exc)
            return cached
        return {
            'checked_at': time.time(),
            'latest_version': '',
            'latest_url': LATEST_RELEASE_PAGE_URL,
            'latest_asset_url': '',
            'latest_asset_name': '',
            'latest_notes': '',
            'error': str(exc)
        }


def _download_release_asset(asset_url, destination_path):
    request = urllib.request.Request(
        asset_url,
        headers={
            'User-Agent': 'BetterParameters',
            'Cache-Control': 'no-cache'
        }
    )
    with urllib.request.urlopen(request, timeout=20) as response, open(destination_path, 'wb') as handle:
        import shutil as _shutil
        _shutil.copyfileobj(response, handle)


def _find_extracted_addin_dir(extract_root):
    direct = os.path.join(extract_root, 'BetterParameters')
    if os.path.isdir(direct):
        return direct

    for entry in os.listdir(extract_root):
        candidate = os.path.join(extract_root, entry, 'BetterParameters')
        if os.path.isdir(candidate):
            return candidate

    return ''


def _updater_script_contents():
    return r'''import os
import shutil


def apply_update(source_dir, target_dir, skip_names=None):
    skip_names = set(skip_names or [])
    os.makedirs(target_dir, exist_ok=True)
    for name in os.listdir(source_dir):
        if name in skip_names:
            continue
        source_path = os.path.join(source_dir, name)
        target_path = os.path.join(target_dir, name)
        if os.path.isdir(source_path):
            os.makedirs(target_path, exist_ok=True)
            apply_update(source_path, target_path, skip_names=None)
        else:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(source_path, target_path)


if __name__ == '__main__':
    import sys
    apply_update(sys.argv[1], sys.argv[2], set(sys.argv[3:]))
'''


def _write_update_helper():
    with open(UPDATE_HELPER_PATH, 'w', encoding='utf-8') as handle:
        handle.write(_updater_script_contents())


def _script_item_for_addin():
    scripts = _safe_call(lambda: app.scripts)
    if not scripts:
        return None
    return _safe_call(lambda: scripts.itemByPath(ADDIN_DIR))


def _current_run_on_startup_enabled(default_value=None):
    script_item = _script_item_for_addin()
    if script_item and bool(_safe_call(lambda: script_item.isAddIn)):
        current_value = _safe_call(lambda: script_item.isRunOnStartup)
        if current_value is not None:
            return bool(current_value)
    if default_value is None:
        return None
    return bool(default_value)


def _set_run_on_startup(enabled):
    script_item = _script_item_for_addin()
    if not script_item or not bool(_safe_call(lambda: script_item.isAddIn)):
        raise RuntimeError('Fusion could not find Better Parameters as an add-in.')
    script_item.isRunOnStartup = bool(enabled)


def _set_manifest_version(version_text):
    if not version_text:
        return
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as handle:
        manifest = json.load(handle)
    manifest['version'] = str(version_text).strip()
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)


def _current_update_state():
    return read_update_state(UPDATE_STATE_PATH)


def _write_current_update_state(state):
    return write_update_state(UPDATE_STATE_PATH, state)


def _transition_staged_update_to_failed(update_state, message):
    failure_state = fail_update_state(update_state, str(message or '').strip())
    _write_current_update_state(failure_state)
    try:
        _set_run_on_startup(startup_preference_after_apply(update_state))
    except Exception:
        pass
    try:
        _set_manifest_version(update_state.get('installed_version') or _current_addin_version())
    except Exception:
        pass
    try:
        shutil.rmtree(PENDING_UPDATE_DIR, ignore_errors=True)
    except Exception:
        pass
    return failure_state


def _stage_update_payload(release_info):
    current_version = _current_addin_version()
    latest_version = release_info.get('latest_version', '')
    asset_url = release_info.get('latest_asset_url', '')
    asset_name = release_info.get('latest_asset_name') or 'BetterParameters-{}.zip'.format(latest_version or 'update')

    if not asset_url:
        raise ValueError('No downloadable release package was found for the latest version.')

    if os.path.isdir(PENDING_UPDATE_DIR):
        shutil.rmtree(PENDING_UPDATE_DIR, ignore_errors=True)
    os.makedirs(PENDING_UPDATE_DIR, exist_ok=True)

    zip_path = os.path.join(PENDING_UPDATE_DIR, asset_name)
    extract_root = os.path.join(PENDING_UPDATE_DIR, 'extracted')
    os.makedirs(extract_root, exist_ok=True)
    _download_release_asset(asset_url, zip_path)
    with zipfile.ZipFile(zip_path, 'r') as archive:
        archive.extractall(extract_root)

    extracted_addin_dir = _find_extracted_addin_dir(extract_root)
    if not extracted_addin_dir:
        raise ValueError('The downloaded release package did not contain a BetterParameters add-in folder.')

    _write_update_helper()
    script_item = _script_item_for_addin()
    previous_run_on_startup = bool(_safe_call(lambda: script_item.isRunOnStartup)) if script_item else False
    update_info = stage_update_state(
        latest_version,
        current_version,
        extracted_addin_dir,
        previous_run_on_startup
    )

    try:
        _set_run_on_startup(True)
        _set_manifest_version(latest_version)
        with open(PENDING_UPDATE_INFO_PATH, 'w', encoding='utf-8') as handle:
            json.dump(update_info, handle, indent=2, sort_keys=True)
        _write_current_update_state(update_info)
        return update_info
    except Exception:
        try:
            _set_run_on_startup(previous_run_on_startup)
        except Exception:
            pass
        try:
            _set_manifest_version(current_version)
        except Exception:
            pass
        try:
            shutil.rmtree(PENDING_UPDATE_DIR, ignore_errors=True)
        except Exception:
            pass
        raise


def _apply_pending_update_if_needed():
    update_state = _current_update_state()
    if update_state.get('state') != STATE_STAGED:
        return None
    if not os.path.exists(PENDING_UPDATE_INFO_PATH) or not os.path.exists(UPDATE_HELPER_PATH):
        message = 'The staged update files are missing.'
        _transition_staged_update_to_failed(update_state, message)
        return {'status': 'failed', 'latest_version': '', 'error': message}

    try:
        with open(PENDING_UPDATE_INFO_PATH, 'r', encoding='utf-8') as handle:
            update_info = normalize_update_state(json.load(handle))
        staged_addin_dir = str(update_info.get('staged_addin_dir') or '').strip()
        latest_version = str(update_info.get('target_version') or '').strip()
        if not staged_addin_dir or not os.path.isdir(staged_addin_dir):
            raise ValueError('The staged update files are missing.')

        spec = importlib.util.spec_from_file_location('better_parameters_update_helper', UPDATE_HELPER_PATH)
        if not spec or not spec.loader:
            raise RuntimeError('Could not load the update helper.')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.apply_update(
            staged_addin_dir,
            ADDIN_DIR,
            {'settings.json', os.path.basename(UPDATE_HELPER_PATH), os.path.basename(PENDING_UPDATE_DIR)}
        )

        pycache_dir = os.path.join(ADDIN_DIR, '__pycache__')
        if os.path.isdir(pycache_dir):
            shutil.rmtree(pycache_dir, ignore_errors=True)

        shutil.rmtree(PENDING_UPDATE_DIR, ignore_errors=True)
        try:
            _set_run_on_startup(startup_preference_after_apply(update_info))
        except Exception:
            pass
        applied_state = applied_update_state(update_info, latest_version or _current_addin_version())
        _write_current_update_state(applied_state)
        return {'status': 'applied', 'latest_version': latest_version or _current_addin_version(), 'error': ''}
    except Exception as exc:
        _transition_staged_update_to_failed(update_state, str(exc))
        return {'status': 'failed', 'latest_version': '', 'error': str(exc)}


def _launch_updated_addin_from_disk(context):
    global _updated_runtime_module
    updated_entry_path = os.path.join(ADDIN_DIR, 'BetterParameters.py')
    module_name = 'better_parameters_updated_main'
    spec = importlib.util.spec_from_file_location(module_name, updated_entry_path)
    if not spec or not spec.loader:
        raise RuntimeError('Could not load the updated Better Parameters entry point.')
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, 'run'):
        raise RuntimeError('The updated Better Parameters entry point did not define run(context).')
    _updated_runtime_module = module
    module.run(context)
