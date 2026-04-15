import json
import importlib
import importlib.util
import hashlib
import os
import platform
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
DOCUMENT_ORDER_DIRNAME = "document_orders"
DEFAULT_PALETTE_WIDTH = 520
DEFAULT_PALETTE_HEIGHT = 640
ATTRIBUTE_NAMESPACE = "BetterParameters"
ATTRIBUTE_PARAMETER_GROUP_NAME = "group"
ATTRIBUTE_METADATA_CHANGED_AT_NAME = "metadataChangedAt"
GROUP_UNGROUPED_LABEL = "Ungrouped"
MAX_GROUP_NAME_LENGTH = 80
METADATA_CHANGED_AT_RECORD_KEY = "metadata_changed_at"
EXPRESSION_TOKEN_PATTERN = re.compile('[A-Za-z_"\\$\\u00B0\\u00B5][A-Za-z0-9_"\\$\\u00B0\\u00B5]*')
ALLOWED_EXPRESSION_IDENTIFIERS = {
    "PI", "E", "Gravity", "SpeedOfLight",
    "if", "and", "or", "not",
    "cos", "sin", "tan", "acos", "acosh", "asin", "asinh", "atan", "atanh",
    "cosh", "sinh", "tanh", "sqrt", "sign", "exp", "floor", "ceil", "round",
    "abs", "max", "min", "ln", "log", "pow", "random",
}
PARAMETER_NAME_PATTERN = re.compile('^[A-Za-z_"\\$\\u00B0\\u00B5][A-Za-z0-9_"\\$\\u00B0\\u00B5]*$')

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
        "actions": 8,
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
    "customUnits": [],
    "showRevertButtons": True,
    "autoFitColumns": True,
    "pinnedUnits": [],
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

    if action == "revertParameter":
        _revert_parameter(data)
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "setParameterFavorite":
        _set_parameter_favorite(data)
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "setParameterGroup":
        _set_parameter_group(data)
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "renameGroup":
        _rename_group(data)
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "deleteGroup":
        _delete_group(data)
        payload = _current_state_payload()
        _send_to_palette("renderState", payload)
        return payload

    if action == "saveParameterOrder":
        _save_parameter_order(data)
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

    if action == "previewExpression":
        return _preview_expression_response(
            data.get("expression", ""),
            data.get("currentParameterName", ""),
            data.get("units", ""),
            data.get("fallbackPreview", "")
        )

    if action == "validateUnit":
        return _validate_unit_response(data.get("unit", ""))

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
    parameters = _collect_user_parameters()
    return {
        "ok": True,
        "parameters": parameters,
        "groups": _collect_parameter_groups(parameters),
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
        "latestNotes": cached.get("latest_notes", ""),
        "autoCheckUpdates": auto_check,
        "updateState": update_state.get("state", "idle"),
        "targetVersion": update_state.get("target_version", ""),
        "installedVersion": update_state.get("installed_version", ""),
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
    order_state = _read_document_order_state()
    saved_records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    results = []
    params = design.userParameters
    for index in range(params.count):
        param = params.item(index)
        if not param:
            continue

        parameter_key = _parameter_entity_token(param)
        saved_record = saved_records.get(parameter_key) or {}
        sort_order = saved_record.get("order")
        if not isinstance(sort_order, int):
            sort_order = params.count + index
        attr_group_name = _parameter_group_name(param)
        attr_metadata_changed_at = _parameter_metadata_changed_at(param)
        saved_group_name = _normalize_group_name(saved_record.get("group") or "")
        saved_metadata_changed_at = _metadata_changed_at_value(saved_record.get(METADATA_CHANGED_AT_RECORD_KEY))
        if attr_metadata_changed_at > saved_metadata_changed_at:
            group_name = attr_group_name
            metadata_changed_at = attr_metadata_changed_at
        elif saved_metadata_changed_at > attr_metadata_changed_at:
            group_name = saved_group_name
            metadata_changed_at = saved_metadata_changed_at
        else:
            group_name = attr_group_name or saved_group_name
            metadata_changed_at = max(attr_metadata_changed_at, saved_metadata_changed_at)

        results.append(
            {
                "key": parameter_key,
                "name": param.name,
                "expression": param.expression,
                "unit": param.unit,
                "comment": param.comment or "",
                "isFavorite": param.isFavorite,
                "group": group_name,
                "valuePreview": _format_parameter_value(param, units_manager),
                "previousExpression": str(saved_record.get("previous_expression") or ""),
                "previousValue": str(saved_record.get("previous_value") or ""),
                "metadataChangedAt": metadata_changed_at,
                "_sortOrder": sort_order,
                "_sourceIndex": index,
            }
        )

    results.sort(key=lambda item: (item.get("_sortOrder", params.count), item.get("_sourceIndex", 0), item.get("name", "").casefold()))
    _persist_document_order_snapshot(results, order_state)
    for item in results:
        item.pop("_sortOrder", None)
        item.pop("_sourceIndex", None)
    return results


def _collect_parameter_groups(parameters):
    names = []
    seen = set()
    for parameter in parameters or []:
        group_name = _normalize_group_name(parameter.get("group") or "")
        if not group_name:
            continue
        folded = group_name.casefold()
        if folded in seen:
            continue
        names.append(group_name)
        seen.add(folded)

    names.sort(key=str.casefold)
    return names


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


def _document_order_root():
    path = _app_support_root() / DOCUMENT_ORDER_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_document_order_dir(path)
    return path


def _app_support_root():
    windows_root = os.getenv("APPDATA")
    if windows_root:
        return Path(windows_root) / "BetterParameters"

    system_name = platform.system().lower()
    home = Path.home()
    if system_name == "darwin":
        return home / "Library" / "Application Support" / "BetterParameters"

    xdg_root = os.getenv("XDG_CONFIG_HOME")
    if xdg_root:
        return Path(xdg_root) / "BetterParameters"

    return home / ".config" / "BetterParameters"


def _legacy_document_order_root():
    return Path(ADDIN_DIR) / DOCUMENT_ORDER_DIRNAME


def _migrate_legacy_document_order_dir(target_root):
    legacy_root = _legacy_document_order_root()
    if legacy_root == target_root or not legacy_root.exists() or not legacy_root.is_dir():
        return

    for legacy_file in legacy_root.glob("*.json"):
        target_file = target_root / legacy_file.name
        if target_file.exists():
            continue
        try:
            shutil.copy2(legacy_file, target_file)
        except Exception:
            continue


def _document_order_storage_key(document_id, document_name):
    basis = (document_id or "").strip() or (document_name or "").strip() or "unsaved-document"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _document_order_path(document_id=None, document_name=None):
    if document_id is None or document_name is None:
        info = _active_document_info()
        document_id = info.get("id", "")
        document_name = info.get("name", "")
    return _document_order_root() / f"{_document_order_storage_key(document_id, document_name)}.json"


def _read_document_order_state():
    info = _active_document_info()
    path = _document_order_path(info.get("id", ""), info.get("name", ""))
    state = {
        "documentId": info.get("id", ""),
        "documentName": info.get("name", ""),
        "parameters": {},
    }
    if not path.exists():
        return state

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return state

    if not isinstance(loaded, dict):
        return state

    records = {}
    loaded_parameters = loaded.get("parameters")
    if isinstance(loaded_parameters, dict):
        for token, record in loaded_parameters.items():
            if not isinstance(token, str) or not token:
                continue
            if not isinstance(record, dict):
                continue
            order_value = record.get("order")
            if not isinstance(order_value, int):
                continue
            records[token] = {
                "order": order_value,
                "name": str(record.get("name") or ""),
                "current_expression": str(record.get("current_expression") or ""),
                "previous_expression": str(record.get("previous_expression") or ""),
                "current_value": str(record.get("current_value") or ""),
                "previous_value": str(record.get("previous_value") or ""),
                "group": _normalize_group_name(record.get("group") or ""),
                METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(record.get(METADATA_CHANGED_AT_RECORD_KEY)),
            }

    state["documentId"] = str(loaded.get("documentId") or state["documentId"])
    state["documentName"] = str(loaded.get("documentName") or state["documentName"])
    state["parameters"] = records
    return state


def _write_document_order_state(state):
    info = _active_document_info()
    document_id = state.get("documentId") if isinstance(state, dict) else ""
    document_name = state.get("documentName") if isinstance(state, dict) else ""
    document_id = str(document_id or info.get("id", ""))
    document_name = str(document_name or info.get("name", ""))
    path = _document_order_path(document_id, document_name)
    payload = {
        "documentId": document_id,
        "documentName": document_name,
        "parameters": state.get("parameters", {}) if isinstance(state, dict) else {},
    }
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _find_user_parameter_by_token(design, token):
    if not design or not token:
        return None

    try:
        found = design.findEntityByToken(token)
    except Exception:
        return None

    parameter = adsk.fusion.UserParameter.cast(found)
    if parameter:
        return parameter

    if isinstance(found, (list, tuple)):
        for item in found:
            parameter = adsk.fusion.UserParameter.cast(item)
            if parameter:
                return parameter

    return None


def _parameter_entity_token(param):
    if not param:
        return ""
    try:
        return param.entityToken or param.name or ""
    except Exception:
        return getattr(param, "name", "") or ""


def _resolve_document_order_records(design, records):
    resolved = {}
    for token, record in (records or {}).items():
        if not isinstance(record, dict):
            continue

        parameter = _find_user_parameter_by_token(design, token)
        current_token = _parameter_entity_token(parameter) if parameter else token
        order_value = record.get("order")
        if not isinstance(order_value, int):
            continue

        resolved[current_token] = {
            "order": order_value,
            "name": parameter.name if parameter and getattr(parameter, "name", "") else str(record.get("name") or ""),
            "current_expression": str(record.get("current_expression") or ""),
            "previous_expression": str(record.get("previous_expression") or ""),
            "current_value": str(record.get("current_value") or ""),
            "previous_value": str(record.get("previous_value") or ""),
            "group": _normalize_group_name(record.get("group") or ""),
            METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(record.get(METADATA_CHANGED_AT_RECORD_KEY)),
        }
    return resolved


def _persist_document_order_snapshot(parameters, previous_state=None):
    info = _active_document_info()
    design = _design()
    records = {}
    previous_records = {}
    if isinstance(previous_state, dict) and isinstance(previous_state.get("parameters"), dict):
        previous_records = previous_state.get("parameters") or {}

    for index, parameter in enumerate(parameters or []):
        key = str(parameter.get("key") or "")
        if not key:
            continue
        previous_record = previous_records.get(key) if isinstance(previous_records.get(key), dict) else {}

        incoming_expression = parameter.get("expression")
        if not isinstance(incoming_expression, str):
            incoming_expression = str(previous_record.get("current_expression") or "")
        incoming_value = parameter.get("valuePreview")
        if not isinstance(incoming_value, str):
            incoming_value = str(previous_record.get("current_value") or "")

        previous_expression = str(previous_record.get("previous_expression") or "")
        previous_value = str(previous_record.get("previous_value") or "")
        previous_group = _normalize_group_name(previous_record.get("group") or "")
        previous_metadata_changed_at = _metadata_changed_at_value(previous_record.get(METADATA_CHANGED_AT_RECORD_KEY))
        old_current_expression = str(previous_record.get("current_expression") or "")
        old_current_value = str(previous_record.get("current_value") or "")
        incoming_group = _normalize_group_name(parameter.get("group") or previous_group)
        incoming_metadata_changed_at = _metadata_changed_at_value(parameter.get("metadataChangedAt"))

        if old_current_expression and old_current_expression != incoming_expression:
            previous_expression = old_current_expression
        if old_current_value and old_current_value != incoming_value:
            previous_value = old_current_value

        has_metadata_change = (
            int(previous_record.get("order") if isinstance(previous_record.get("order"), int) else -1) != index
            or str(previous_record.get("name") or "") != str(parameter.get("name") or "")
            or str(previous_record.get("current_expression") or "") != incoming_expression
            or str(previous_record.get("previous_expression") or "") != previous_expression
            or str(previous_record.get("current_value") or "") != incoming_value
            or str(previous_record.get("previous_value") or "") != previous_value
            or _normalize_group_name(previous_record.get("group") or "") != incoming_group
        )
        touch_attribute_timestamp = False
        if has_metadata_change:
            if incoming_metadata_changed_at > previous_metadata_changed_at:
                metadata_changed_at = incoming_metadata_changed_at
            else:
                metadata_changed_at = _now_metadata_timestamp_ms()
                touch_attribute_timestamp = True
        else:
            metadata_changed_at = max(previous_metadata_changed_at, incoming_metadata_changed_at)
            if metadata_changed_at <= 0:
                metadata_changed_at = _now_metadata_timestamp_ms()

        records[key] = {
            "order": index,
            "name": str(parameter.get("name") or ""),
            "current_expression": incoming_expression,
            "previous_expression": previous_expression,
            "current_value": incoming_value,
            "previous_value": previous_value,
            "group": incoming_group,
            METADATA_CHANGED_AT_RECORD_KEY: metadata_changed_at,
        }
        if touch_attribute_timestamp and design:
            parameter_entity = _find_user_parameter_by_token(design, key)
            if parameter_entity:
                _set_parameter_metadata_changed_at(parameter_entity, metadata_changed_at)

    next_state = {
        "documentId": info.get("id", ""),
        "documentName": info.get("name", ""),
        "parameters": records,
    }
    if previous_state == next_state:
        return
    _write_document_order_state(next_state)


def _load_settings():
    settings = dict(DEFAULT_SETTINGS)
    settings["paletteSize"] = dict(DEFAULT_SETTINGS["paletteSize"])
    settings["parameterTableColumns"] = dict(DEFAULT_SETTINGS["parameterTableColumns"])
    settings["unitCategoryState"] = dict(DEFAULT_SETTINGS["unitCategoryState"])
    settings["customUnits"] = []
    settings["showRevertButtons"] = bool(DEFAULT_SETTINGS["showRevertButtons"])
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

        if isinstance(loaded.get("customUnits"), list):
            deduped_units = []
            seen_units = set()
            for candidate in loaded["customUnits"]:
                if not isinstance(candidate, str):
                    continue
                token = candidate.strip()
                if not token:
                    continue
                folded = token.casefold()
                if folded in seen_units:
                    continue
                deduped_units.append(token)
                seen_units.add(folded)
                if len(deduped_units) >= 40:
                    break
            settings["customUnits"] = deduped_units

        if isinstance(loaded.get("showRevertButtons"), bool):
            settings["showRevertButtons"] = loaded["showRevertButtons"]

        if isinstance(loaded.get("autoFitColumns"), bool):
            settings["autoFitColumns"] = loaded["autoFitColumns"]

        if isinstance(loaded.get("pinnedUnits"), list):
            deduped_pinned = []
            seen_pinned = set()
            for candidate in loaded["pinnedUnits"]:
                if not isinstance(candidate, str):
                    continue
                token = candidate.strip()
                if not token:
                    continue
                folded = token.casefold()
                if folded in seen_pinned:
                    continue
                deduped_pinned.append(token)
                seen_pinned.add(folded)
                if len(deduped_pinned) >= 40:
                    break
            settings["pinnedUnits"] = deduped_pinned

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

    custom_units = data.get("customUnits")
    if custom_units is not None:
        if not isinstance(custom_units, list):
            raise ValueError('"customUnits" must be an array.')
        deduped_units = []
        seen_units = set()
        for candidate in custom_units:
            if not isinstance(candidate, str):
                continue
            token = candidate.strip()
            if not token:
                continue
            folded = token.casefold()
            if folded in seen_units:
                continue
            deduped_units.append(token)
            seen_units.add(folded)
            if len(deduped_units) >= 40:
                break
        settings["customUnits"] = deduped_units

    if "showRevertButtons" in data:
        show_revert_buttons = data.get("showRevertButtons")
        if not isinstance(show_revert_buttons, bool):
            raise ValueError('"showRevertButtons" must be a boolean.')
        settings["showRevertButtons"] = show_revert_buttons

    if "autoFitColumns" in data:
        auto_fit_columns = data.get("autoFitColumns")
        if not isinstance(auto_fit_columns, bool):
            raise ValueError('"autoFitColumns" must be a boolean.')
        settings["autoFitColumns"] = auto_fit_columns

    if "pinnedUnits" in data:
        if not isinstance(data["pinnedUnits"], list):
            raise ValueError('"pinnedUnits" must be an array.')
        deduped_pinned = []
        seen_pinned = set()
        for candidate in data["pinnedUnits"]:
            if not isinstance(candidate, str):
                continue
            token = candidate.strip()
            if not token:
                continue
            folded = token.casefold()
            if folded in seen_pinned:
                continue
            deduped_pinned.append(token)
            seen_pinned.add(folded)
            if len(deduped_pinned) >= 40:
                break
        settings["pinnedUnits"] = deduped_pinned

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


def _format_preview_value(value, unit, units_manager):
    try:
        if unit:
            return units_manager.formatValue(value, unit, -1, adsk.core.BooleanOptions.DefaultBooleanOption, -1, True)
    except Exception:
        pass

    try:
        rounded = round(float(value), 9)
        if rounded == int(rounded):
            return str(int(rounded))
        return "{:g}".format(rounded)
    except Exception:
        return str(value or "")


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


def _revert_parameter(data):
    design = _require_design()
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    if not key and not name:
        raise ValueError('Either "key" or "name" is required.')

    parameter = _find_user_parameter_by_token(design, key) if key else None
    if not parameter and name:
        parameter = design.userParameters.itemByName(name)
    if not parameter:
        raise ValueError("User parameter was not found.")

    order_state = _read_document_order_state()
    stored_records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    parameter_key = _parameter_entity_token(parameter)
    record = stored_records.get(parameter_key) or {}
    previous_expression = str(record.get("previous_expression") or "").strip()
    if not previous_expression:
        raise ValueError("No previous expression is available to revert.")

    units_manager = design.unitsManager
    current_expression = str(parameter.expression or "")
    current_value = _format_parameter_value(parameter, units_manager)

    parameter.expression = previous_expression
    if "comment" in data:
        parameter.comment = str(data.get("comment") or "")

    reverted_value = _format_parameter_value(parameter, units_manager)
    order_value = record.get("order")
    if not isinstance(order_value, int):
        order_value = len(stored_records)
    metadata_changed_at = _now_metadata_timestamp_ms()

    stored_records[parameter_key] = {
        "order": order_value,
        "name": str(parameter.name or ""),
        "current_expression": str(parameter.expression or ""),
        "previous_expression": current_expression,
        "current_value": reverted_value,
        "previous_value": current_value,
        "group": _normalize_group_name(record.get("group") or _parameter_group_name(parameter) or ""),
        METADATA_CHANGED_AT_RECORD_KEY: metadata_changed_at,
    }
    _set_parameter_metadata_changed_at(parameter, metadata_changed_at)
    _write_document_order_state(
        {
            "documentId": order_state.get("documentId", ""),
            "documentName": order_state.get("documentName", ""),
            "parameters": stored_records,
        }
    )


def _set_parameter_favorite(data):
    design = _require_design()
    name = _required_text(data, "name")
    is_favorite = bool(data.get("isFavorite"))

    param = design.userParameters.itemByName(name)
    if not param:
        raise ValueError(f'User parameter "{name}" was not found.')

    param.isFavorite = is_favorite


def _set_parameter_group(data):
    design = _require_design()
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    if not key and not name:
        raise ValueError('Either "key" or "name" is required.')

    group_name = _normalize_group_name(data.get("group") or "")
    parameter = _find_user_parameter_by_token(design, key) if key else None
    if not parameter and name:
        parameter = design.userParameters.itemByName(name)
    if not parameter:
        raise ValueError("User parameter was not found.")
    metadata_changed_at = _now_metadata_timestamp_ms()
    _write_parameter_group_name(parameter, group_name, metadata_changed_at)
    _set_parameter_group_record(design, parameter, group_name, metadata_changed_at)


def _rename_group(data):
    design = _require_design()
    old_group = _normalize_group_name(_required_text(data, "oldGroup"))
    if not old_group:
        raise ValueError("Ungrouped cannot be renamed.")

    new_group = _normalize_group_name(_required_text(data, "newGroup"))
    if not new_group:
        raise ValueError("Ungrouped cannot be used as a rename target.")
    if old_group.casefold() == new_group.casefold():
        return

    params = design.userParameters
    metadata_changed_at = _now_metadata_timestamp_ms()
    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue
        existing_group = _parameter_group_name(parameter)
        if not existing_group:
            existing_group = _parameter_group_from_record(design, parameter)
        if existing_group.casefold() != old_group.casefold():
            continue
        _write_parameter_group_name(parameter, new_group, metadata_changed_at)
        _set_parameter_group_record(design, parameter, new_group, metadata_changed_at)


def _delete_group(data):
    design = _require_design()
    group_name = _normalize_group_name(_required_text(data, "group"))
    if not group_name:
        raise ValueError("Ungrouped cannot be deleted.")

    params = design.userParameters
    metadata_changed_at = _now_metadata_timestamp_ms()
    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue
        existing_group = _parameter_group_name(parameter)
        if not existing_group:
            existing_group = _parameter_group_from_record(design, parameter)
        if existing_group.casefold() != group_name.casefold():
            continue
        _write_parameter_group_name(parameter, "", metadata_changed_at)
        _set_parameter_group_record(design, parameter, "", metadata_changed_at)


def _save_parameter_order(data):
    design = _require_design()
    keys = data.get("keys")
    if not isinstance(keys, list):
        raise ValueError('"keys" must be an array.')

    ordered_keys = []
    seen = set()
    for key in keys:
        key_text = str(key or "").strip()
        if not key_text or key_text in seen:
            continue
        ordered_keys.append(key_text)
        seen.add(key_text)

    current_parameters = []
    params = design.userParameters
    for index in range(params.count):
        param = params.item(index)
        if not param:
            continue
        current_parameters.append(
            {
                "key": _parameter_entity_token(param),
                "name": param.name,
            }
        )

    current_by_key = {item["key"]: item for item in current_parameters if item.get("key")}
    merged = []
    for key in ordered_keys:
        item = current_by_key.pop(key, None)
        if item:
            merged.append(item)

    merged.extend(current_parameters_item for current_parameters_item in current_parameters if current_parameters_item.get("key") in current_by_key)
    _persist_document_order_snapshot(merged, _read_document_order_state())


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

    design = _design()
    if design:
        try:
            validate_units = units or design.unitsManager.defaultLengthUnits or "mm"
            if design.unitsManager.isValidExpression(text, validate_units):
                return {"ok": True, "message": ""}
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
            if not design.unitsManager.isValidExpression(text, validate_units):
                incomplete_hint = _incomplete_expression_hint(text)
                if incomplete_hint:
                    return {
                        "ok": False,
                        "message": incomplete_hint,
                        "isIncomplete": True,
                    }
                return {
                    "ok": False,
                    "message": "Expression syntax is invalid. Use explicit operators between terms; parentheses do not imply multiplication."
                }
        except Exception:
            pass

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

    return {"ok": True, "message": ""}


def _incomplete_expression_hint(text):
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        return "Expression is required."

    if stripped.endswith(("(", ",", ";")):
        return "Expression looks incomplete. Keep typing inside the current parentheses."

    if stripped.endswith(("+", "-", "*", "/", "^")):
        return f'Expression looks incomplete after "{stripped[-1]}". Add the next value or parameter.'

    if stripped.endswith((">", "<", "=", "!", "&", "|")):
        return "Expression looks incomplete after a comparison/logical operator. Continue the right-hand side."

    open_count = 0
    for char in stripped:
        if char == "(":
            open_count += 1
        elif char == ")" and open_count > 0:
            open_count -= 1
    if open_count > 0:
        return "Expression has an open parenthesis. Finish the expression and close it."

    return ""


def _preview_expression_response(expression, current_parameter_name="", units="", fallback_preview=""):
    validation = _validate_expression_response(expression, current_parameter_name, units)
    if not validation["ok"]:
        return {
            "ok": False,
            "message": validation["message"],
            "preview": str(fallback_preview or "")
        }

    design = _design()
    if not design:
        return {
            "ok": False,
            "message": "No active Fusion design is available.",
            "preview": str(fallback_preview or "")
        }

    units_manager = design.unitsManager
    preview_unit = str(units or "").strip()
    if not preview_unit and current_parameter_name:
        try:
            current_param = design.userParameters.itemByName(current_parameter_name)
            if current_param:
                preview_unit = current_param.unit or ""
        except Exception:
            preview_unit = ""

    evaluate_units = preview_unit or units_manager.defaultLengthUnits or "mm"
    try:
        value = units_manager.evaluateExpression(str(expression or "").strip(), evaluate_units)
        return {
            "ok": True,
            "message": "",
            "preview": _format_preview_value(value, preview_unit, units_manager)
        }
    except Exception:
        return {
            "ok": False,
            "message": "Fusion could not evaluate that expression yet.",
            "preview": str(fallback_preview or "")
        }


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


def _validate_unit_response(unit_text):
    unit = str(unit_text or "").strip()
    if not unit:
        return {"ok": False, "message": "Unit is required."}

    if unit.casefold() == "text":
        return {"ok": True, "message": "", "unit": "Text"}

    design = _design()
    if not design:
        return {"ok": True, "message": "", "unit": unit}

    units_manager = design.unitsManager
    try:
        if units_manager.isValidExpression("1", unit) or units_manager.isValidExpression(f"1 {unit}", unit):
            try:
                formatted = units_manager.formatUnits(unit) or unit
                return {"ok": True, "message": "", "unit": formatted.strip() or unit}
            except Exception:
                return {"ok": True, "message": "", "unit": unit}
    except Exception:
        pass

    return {"ok": False, "message": f'"{unit}" is not a valid Fusion unit.', "unit": ""}


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


def _now_metadata_timestamp_ms():
    return int(time.time() * 1000)


def _metadata_changed_at_value(value):
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float):
        parsed = int(value)
        return parsed if parsed > 0 else 0
    try:
        parsed = int(str(value or "").strip())
        return parsed if parsed > 0 else 0
    except Exception:
        return 0


def _normalize_group_name(value):
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    if text.casefold() == GROUP_UNGROUPED_LABEL.casefold():
        return ""
    if len(text) > MAX_GROUP_NAME_LENGTH:
        text = text[:MAX_GROUP_NAME_LENGTH].strip()
    return text


def _parameter_group_name(parameter):
    if not parameter:
        return ""

    attributes = getattr(parameter, "attributes", None)
    if not attributes:
        return ""

    try:
        attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_PARAMETER_GROUP_NAME)
    except Exception:
        attribute = None

    if not attribute:
        return ""

    try:
        return _normalize_group_name(attribute.value)
    except Exception:
        return ""


def _parameter_metadata_changed_at(parameter):
    if not parameter:
        return 0

    attributes = getattr(parameter, "attributes", None)
    if not attributes:
        return 0

    try:
        attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_METADATA_CHANGED_AT_NAME)
    except Exception:
        attribute = None

    if not attribute:
        return 0

    try:
        return _metadata_changed_at_value(attribute.value)
    except Exception:
        return 0


def _set_parameter_metadata_changed_at(parameter, metadata_changed_at):
    if not parameter:
        return False

    metadata_changed_at_value = _metadata_changed_at_value(metadata_changed_at)
    if metadata_changed_at_value <= 0:
        return False

    attributes = getattr(parameter, "attributes", None)
    if not attributes:
        return False

    try:
        attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_METADATA_CHANGED_AT_NAME)
    except Exception:
        attribute = None

    if attribute:
        try:
            attribute.value = str(metadata_changed_at_value)
            return True
        except Exception:
            pass

    try:
        attributes.add(ATTRIBUTE_NAMESPACE, ATTRIBUTE_METADATA_CHANGED_AT_NAME, str(metadata_changed_at_value))
        return True
    except Exception:
        return False


def _write_parameter_group_name(parameter, group_name, metadata_changed_at=None):
    if not parameter:
        return

    normalized_group = _normalize_group_name(group_name)
    metadata_changed_at_value = _metadata_changed_at_value(metadata_changed_at)
    attributes = getattr(parameter, "attributes", None)
    if not attributes:
        return

    try:
        attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_PARAMETER_GROUP_NAME)
    except Exception:
        attribute = None

    if attribute:
        try:
            attribute.value = normalized_group
            if metadata_changed_at_value > 0:
                _set_parameter_metadata_changed_at(parameter, metadata_changed_at_value)
            return True
        except Exception:
            if not normalized_group:
                try:
                    attribute.deleteMe()
                    if metadata_changed_at_value > 0:
                        _set_parameter_metadata_changed_at(parameter, metadata_changed_at_value)
                    return True
                except Exception:
                    pass

    if not normalized_group:
        if metadata_changed_at_value > 0:
            _set_parameter_metadata_changed_at(parameter, metadata_changed_at_value)
        return True

    try:
        attributes.add(ATTRIBUTE_NAMESPACE, ATTRIBUTE_PARAMETER_GROUP_NAME, normalized_group)
        if metadata_changed_at_value > 0:
            _set_parameter_metadata_changed_at(parameter, metadata_changed_at_value)
        return True
    except Exception:
        return False


def _parameter_group_from_record(design, parameter):
    if not design or not parameter:
        return ""

    parameter_key = _parameter_entity_token(parameter)
    if not parameter_key:
        return ""

    state = _read_document_order_state()
    records = _resolve_document_order_records(design, state.get("parameters") or {})
    record = records.get(parameter_key) if isinstance(records.get(parameter_key), dict) else {}
    return _normalize_group_name(record.get("group") or "")


def _set_parameter_group_record(design, parameter, group_name, metadata_changed_at=None):
    if not design or not parameter:
        return

    parameter_key = _parameter_entity_token(parameter)
    if not parameter_key:
        return

    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    existing_record = records.get(parameter_key) if isinstance(records.get(parameter_key), dict) else {}
    order_value = existing_record.get("order")
    if not isinstance(order_value, int):
        order_value = len(records)
    resolved_metadata_changed_at = _metadata_changed_at_value(metadata_changed_at)
    if resolved_metadata_changed_at <= 0:
        resolved_metadata_changed_at = _metadata_changed_at_value(existing_record.get(METADATA_CHANGED_AT_RECORD_KEY))
    if resolved_metadata_changed_at <= 0:
        resolved_metadata_changed_at = _now_metadata_timestamp_ms()

    units_manager = design.unitsManager
    records[parameter_key] = {
        "order": order_value,
        "name": str(parameter.name or ""),
        "current_expression": str(existing_record.get("current_expression") or parameter.expression or ""),
        "previous_expression": str(existing_record.get("previous_expression") or ""),
        "current_value": str(existing_record.get("current_value") or _format_parameter_value(parameter, units_manager)),
        "previous_value": str(existing_record.get("previous_value") or ""),
        "group": _normalize_group_name(group_name or ""),
        METADATA_CHANGED_AT_RECORD_KEY: resolved_metadata_changed_at,
    }

    _write_document_order_state(
        {
            "documentId": order_state.get("documentId", ""),
            "documentName": order_state.get("documentName", ""),
            "parameters": records,
        }
    )


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
        with open(MANIFEST_PATH, 'r', encoding='utf-8-sig') as handle:
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

    for root, _dirs, files in os.walk(extract_root):
        required = {'BetterParameters.py', 'palette.html', 'BetterParameters.manifest'}
        if required.issubset(set(files)):
            return root

    return ''


def _extract_release_archive(zip_path, extract_root):
    with zipfile.ZipFile(zip_path, 'r') as archive:
        for member in archive.infolist():
            normalized_name = str(member.filename or '').replace('\\', '/').strip('/')
            if not normalized_name:
                continue

            parts = [part for part in normalized_name.split('/') if part not in {'', '.', '..'}]
            if not parts:
                continue

            destination = os.path.join(extract_root, *parts)
            if member.is_dir():
                os.makedirs(destination, exist_ok=True)
                continue

            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with archive.open(member, 'r') as source_handle, open(destination, 'wb') as target_handle:
                shutil.copyfileobj(source_handle, target_handle)


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
    with open(MANIFEST_PATH, 'r', encoding='utf-8-sig') as handle:
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
    _extract_release_archive(zip_path, extract_root)

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
