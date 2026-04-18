import csv
import ctypes
import io
import json
import importlib
import importlib.util
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import uuid
import webbrowser
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
TEXT_TUNER_STATE_FILE = "text_tuner_temp.json"
DOCUMENT_ORDER_DIRNAME = "document_orders"
DEFAULT_PALETTE_WIDTH = 520
DEFAULT_PALETTE_HEIGHT = 640
ATTRIBUTE_NAMESPACE = "BetterParameters"
ATTRIBUTE_PARAMETER_GROUP_NAME = "group"
ATTRIBUTE_METADATA_CHANGED_AT_NAME = "metadataChangedAt"
ATTRIBUTE_METADATA_REVISION_NAME = "metadataRevision"
ATTRIBUTE_METADATA_WRITER_ID_NAME = "metadataWriterId"
ATTRIBUTE_METADATA_WRITER_VERSION_NAME = "metadataWriterVersion"
ATTRIBUTE_DOCUMENT_METADATA_MAP_NAME = "parameterMetadataMap"
ATTRIBUTE_DOCUMENT_METADATA_STATE_NAME = "metadataState"
ATTRIBUTE_DOCUMENT_METADATA_ITEM_NAMESPACE = "BetterParametersMeta"
GROUP_UNGROUPED_LABEL = "Ungrouped"
MAX_GROUP_NAME_LENGTH = 80
METADATA_CHANGED_AT_RECORD_KEY = "metadata_changed_at"
METADATA_REVISION_RECORD_KEY = "metadata_revision"
METADATA_WRITER_ID_RECORD_KEY = "metadata_writer_id"
METADATA_WRITER_VERSION_RECORD_KEY = "metadata_writer_version"
METADATA_SCHEMA_VERSION = 2
BPMETA_SCHEMA_VERSION = 1
UI_STATE_RECORD_KEY = "uiState"
UI_STATE_REVISION_KEY = "revision"
UI_STATE_CHANGED_AT_KEY = "changedAt"
UI_STATE_WRITER_ID_KEY = "writerId"
UI_STATE_WRITER_VERSION_KEY = "writerVersion"
EXPRESSION_TOKEN_PATTERN = re.compile('[A-Za-z_"\\$\\u00B0\\u00B5][A-Za-z0-9_"\\$\\u00B0\\u00B5]*')
ALLOWED_EXPRESSION_IDENTIFIERS = {
    "PI", "E", "Gravity", "SpeedOfLight",
    "if", "and", "or", "not",
    "cos", "sin", "tan", "acos", "acosh", "asin", "asinh", "atan", "atanh",
    "cosh", "sinh", "tanh", "sqrt", "sign", "exp", "floor", "ceil", "round",
    "abs", "max", "min", "ln", "log", "pow", "random",
}

# Probe units used to conservatively detect "valid expression, wrong dimension" cases.
# If an expression is invalid for the target unit but valid for one of these probes,
# we can report likely unit/dimension mismatch instead of generic syntax failure.
DIMENSION_PROBE_UNITS = [
    "mm",      # length
    "deg",     # angle
    "mm^2",    # area
    "mm^3",    # volume
    "kg",      # mass
    "s",       # time
    "m/s",     # velocity
    "m/s^2",   # acceleration
    "N",       # force
    "Pa",      # pressure
    "W",       # power
]
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
    "palettePosition": {},
    "paletteDockingState": "floating",
    "parameterTableColumns": {
        "parameter": 140,
        "name": 180,
        "unit": 80,
        "expression": 220,
        "value": 120,
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
    "showCommentColumn": False,
    "showTextTunerSidebar": True,
    "autoFitColumns": True,
    "pinnedUnits": [],
    "autoCheckUpdates": True,
    "updateCheck": {},
    "autoOpenOnStart": False,
}
# Maps new parameterTableColumns key names → old key names stored in settings before the rename.
# Used in _load_settings to migrate settings files written before the column key rename.
_COLUMN_KEY_OLD_NAMES = {
    "parameter": "name",
    "name": "expression",
    "unit": "preview",
    "expression": "comment",
    "value": "actions",
}

ALLOWED_PALETTE_DOCKING_STATE_NAMES = {"floating", "left", "right", "top", "bottom"}
TARGET_PANEL_IDS = [
    PANEL_ID,
    "SolidModifyPanel",
    "SurfaceModifyPanel",
    "MeshModifyPanel",
    "SheetMetalModifyPanel",
    "PlasticModifyPanel",
]


CONTRACT_VERSION = "2026-04-17"

_READ_ONLY_ACTIONS = [
    "ready", "refresh", "validateParameterName", "validateExpression",
    "previewExpression", "validateUnit", "openHelpUrl",
    "getActiveDocumentInfo", "checkForUpdates", "getMetadataDebugSnapshot",
    "validateParametersPackageImport", "exportParameters", "exportParametersPackage",
    "getParameterDependencyGraph", "getBackendContractInfo", "runSelfTestSuite",
    "copyToClipboard", "getModelParameters",
]

_MUTATING_ACTIONS = [
    "updateParameter", "revertParameter", "setParameterFavorite",
    "setParameterGroup", "renameGroup", "deleteGroup",
    "saveParameterOrder", "saveGroupUiState", "createParameter",
    "deleteParameter", "deleteParameters", "renameParameter",
    "updateModelParameter", "copyParameter", "sortByTimelineOrder",
    "importParameters", "saveSettings", "savePaletteGeometry",
    "saveTextTunerState", "downloadAndStageUpdate",
    "syncMetadataJsonToFusion", "syncMetadataFusionToJson", "repairMetadata",
    "importParametersPackage", "seedTestParameters", "resetTestState",
    "batchUpdateParameters",
]

# ---------------------------------------------------------------------------
# Error codes — stable identifiers for ok:false responses.
# ---------------------------------------------------------------------------
ERROR_VALIDATION = "VALIDATION_ERROR"
ERROR_CONFLICT = "CONFLICT_ERROR"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_IO = "IO_ERROR"
ERROR_DIALOG_CANCELLED = "DIALOG_CANCELLED"
ERROR_TRANSPORT = "TRANSPORT_ERROR"
ERROR_CONTRACT = "CONTRACT_ERROR"
ERROR_NO_DESIGN = "NO_DESIGN"
ERROR_UNKNOWN = "UNKNOWN_ERROR"


class BPError(Exception):
    """BetterParameters exception carrying a stable error code."""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.bp_code = code or ERROR_UNKNOWN


class BPValidationError(BPError):
    def __init__(self, message):
        super().__init__(message, ERROR_VALIDATION)


class BPConflictError(BPError):
    def __init__(self, message):
        super().__init__(message, ERROR_CONFLICT)


class BPNotFoundError(BPError):
    def __init__(self, message):
        super().__init__(message, ERROR_NOT_FOUND)


class BPIOError(BPError):
    def __init__(self, message):
        super().__init__(message, ERROR_IO)


class BPNoDesignError(BPError):
    def __init__(self):
        super().__init__("Open a Fusion design before using Better Parameters.", ERROR_NO_DESIGN)


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
        threading.Thread(target=_background_update_check, daemon=True).start()

        try:
            if _load_settings().get("autoOpenOnStart", False):
                palette = _ensure_palette()
                palette.isVisible = True
        except Exception:
            pass
    except Exception:
        _message_box(f"Add-in start failed:\n{traceback.format_exc()}")


def stop(_context):
    try:
        palette = _palette()
        if palette:
            _save_palette_geometry(palette)
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
                _send_to_palette("renderState", _ok_state(_current_state_payload()))
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
                        "errorCode": getattr(exc, "bp_code", ERROR_UNKNOWN),
                        "traceback": traceback.format_exc(),
                        "state": None,
                    }
                )


class PaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, _args):
        try:
            palette = _palette()
            if palette:
                _save_palette_geometry(palette)
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
    _apply_saved_palette_docking_state(palette)
    _apply_saved_palette_size(palette)
    _apply_saved_palette_position(palette)

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


def _ok_state(state):
    """Uniform success envelope for actions that return updated application state."""
    return {"ok": True, "message": "", "state": state}


def _ok_data(**kwargs):
    """Uniform success envelope for read-only / validation actions (no state change)."""
    return {"ok": True, "message": "", "state": None, **kwargs}


def _handle_palette_action(action, data):
    if action in ("ready", "refresh"):
        return _ok_state(_current_state_payload())

    if action == "updateParameter":
        _update_parameter(data)
        return _ok_state(_current_state_payload())

    if action == "batchUpdateParameters":
        result = _batch_update_parameters(data)
        state = _current_state_payload() if result["ok"] else None
        return {**result, "state": state}

    if action == "revertParameter":
        _revert_parameter(data)
        return _ok_state(_current_state_payload())

    if action == "setParameterFavorite":
        _set_parameter_favorite(data)
        return _ok_state(_current_state_payload())

    if action == "setParameterGroup":
        _set_parameter_group(data)
        return _ok_state(_current_state_payload())

    if action == "renameGroup":
        _rename_group(data)
        return _ok_state(_current_state_payload())

    if action == "deleteGroup":
        _delete_group(data)
        return _ok_state(_current_state_payload())

    if action == "saveParameterOrder":
        _save_parameter_order(data)
        return _ok_state(_current_state_payload())

    if action == "saveGroupUiState":
        _save_group_ui_state(data)
        return _ok_state(_current_state_payload())

    if action == "createParameter":
        _create_parameter(data)
        return _ok_state(_current_state_payload())

    if action == "deleteParameter":
        _delete_parameter(data)
        return _ok_state(_current_state_payload())

    if action == "deleteParameters":
        result = _delete_parameters_batch(data)
        return {**result, "state": _current_state_payload() if result["ok"] else None}

    if action == "renameParameter":
        _rename_parameter(data)
        return _ok_state(_current_state_payload())

    if action == "updateModelParameter":
        _update_model_parameter(data)
        return _ok_state(_current_state_payload())

    if action == "copyParameter":
        _copy_parameter(data)
        return _ok_state(_current_state_payload())

    if action == "sortByTimelineOrder":
        _sort_by_timeline_order()
        return _ok_state(_current_state_payload())

    if action == "exportParameters":
        result = _export_parameters(data)
        if result.get("cancelled"):
            return {"ok": False, "message": "Export cancelled.", "errorCode": ERROR_DIALOG_CANCELLED, "state": None, "exportedCount": 0, "filePath": ""}
        return _ok_data(exportedCount=result["exportedCount"], filePath=result["filePath"])

    if action == "importParameters":
        dry_run = bool(data.get("dryRun", False))
        result = _import_parameters(data, dry_run=dry_run)
        state = _current_state_payload() if (result["ok"] and not dry_run) else None
        return {
            "ok": result["ok"],
            "message": result["message"],
            "state": state,
            "filePath": result.get("filePath", ""),
            "importedCount": result["importedCount"],
            "skippedCount": result["skippedCount"],
            "failedCount": result["failedCount"],
            "failedRows": result["failedRows"],
            "dryRun": dry_run,
        }

    if action == "exportParametersPackage":
        result = _export_parameters_package(data)
        if result.get("cancelled"):
            return {"ok": False, "message": "Export cancelled.", "errorCode": ERROR_DIALOG_CANCELLED, "state": None, "exportedCount": 0, "filePath": "", "format": "bpmeta.json"}
        return _ok_data(exportedCount=result["exportedCount"], filePath=result["filePath"], format="bpmeta.json")

    if action == "validateParametersPackageImport":
        result = _validate_parameters_package_import(data)
        if result.get("cancelled"):
            return {"ok": False, "message": "Import cancelled.", "errorCode": ERROR_DIALOG_CANCELLED, "state": None, "filePath": "", "preview": None}
        return {"ok": True, "message": "", "state": None, "filePath": result["filePath"], "preview": result["preview"]}

    if action == "importParametersPackage":
        dry_run = bool(data.get("dryRun", False))
        result = _import_parameters_package(data, dry_run=dry_run)
        if result.get("cancelled"):
            return {
                "ok": False, "message": "Import cancelled.", "errorCode": ERROR_DIALOG_CANCELLED, "state": None,
                "filePath": "",
                "importedCount": 0, "updatedCount": 0, "skippedCount": 0, "failedCount": 0, "failedRows": [],
                "dryRun": dry_run,
            }
        state = _current_state_payload() if (result["ok"] and not dry_run) else None
        return {
            "ok": result["ok"],
            "message": result["message"],
            "state": state,
            "filePath": result.get("filePath", ""),
            "importedCount": result["importedCount"],
            "updatedCount": result["updatedCount"],
            "skippedCount": result["skippedCount"],
            "failedCount": result["failedCount"],
            "failedRows": result["failedRows"],
            "dryRun": dry_run,
        }

    if action == "saveSettings":
        settings = _save_settings(data)
        return _ok_state(_current_state_payload(settings=settings))

    if action == "savePaletteGeometry":
        geometry = {k: data[k] for k in ("paletteSize", "palettePosition", "paletteDockingState") if k in data}
        settings = _save_settings(geometry)
        return _ok_state(_current_state_payload(settings=settings))

    if action == "getTextTunerState":
        return _ok_data(values=_load_text_tuner_state())

    if action == "saveTextTunerState":
        values = data.get("values") if isinstance(data, dict) else {}
        _save_text_tuner_state(values)
        return _ok_state(_current_state_payload())

    if action == "validateParameterName":
        result = _validate_parameter_name_response(data.get("name", ""))
        return {**result, "state": None}

    if action == "validateExpression":
        result = _validate_expression_response(
            data.get("expression", ""),
            data.get("currentParameterName", ""),
            data.get("units", "")
        )
        return {**result, "state": None}

    if action == "previewExpression":
        result = _preview_expression_response(
            data.get("expression", ""),
            data.get("currentParameterName", ""),
            data.get("units", ""),
            data.get("fallbackPreview", "")
        )
        return {**result, "state": None}

    if action == "validateUnit":
        result = _validate_unit_response(data.get("unit", ""))
        return {**result, "state": None}

    if action == "openHelpUrl":
        result = _open_help_url(data)
        return {**result, "state": None}

    if action == "copyToClipboard":
        result = _copy_to_clipboard(data)
        return {**result, "state": None}

    if action == "getActiveDocumentInfo":
        return _ok_data(document=_active_document_info())

    if action == "checkForUpdates":
        release_info = _latest_release_info(force_refresh=True)
        _save_update_check(release_info)
        return _ok_state(_current_state_payload())

    if action == "downloadAndStageUpdate":
        release_info = _latest_release_info(force_refresh=True, allow_cached_on_error=False)
        _stage_update_payload(release_info)
        return _ok_state(_current_state_payload())

    if action == "getMetadataDebugSnapshot":
        return _ok_data(debugMetadata=_collect_metadata_debug_snapshot())

    if action == "syncMetadataJsonToFusion":
        sync_result = _sync_metadata_json_to_fusion()
        return {
            **_ok_state(_current_state_payload()),
            "syncResult": sync_result,
            "debugMetadata": _collect_metadata_debug_snapshot(),
        }

    if action == "syncMetadataFusionToJson":
        sync_result = _sync_metadata_fusion_to_json()
        return {
            **_ok_state(_current_state_payload()),
            "syncResult": sync_result,
            "debugMetadata": _collect_metadata_debug_snapshot(),
        }

    if action == "repairMetadata":
        sync_result = _repair_metadata()
        return {
            **_ok_state(_current_state_payload()),
            "syncResult": sync_result,
            "debugMetadata": _collect_metadata_debug_snapshot(),
        }

    if action == "getModelParameters":
        result = _get_model_parameters(data)
        return {**result, "state": None}

    if action == "getParameterDependencyGraph":
        graph = _get_parameter_dependency_graph()
        return _ok_data(nodes=graph["nodes"], edges=graph["edges"])

    if action == "getBackendContractInfo":
        return _ok_data(**_get_backend_contract_info())

    if action == "seedTestParameters":
        result = _seed_test_parameters(data)
        state = _current_state_payload() if result["ok"] else None
        return {
            "ok": result["ok"],
            "message": result["message"],
            "state": state,
            "seededCount": result["seededCount"],
            "failedRows": result["failedRows"],
        }

    if action == "resetTestState":
        result = _reset_test_state(data)
        return {
            **_ok_state(_current_state_payload()),
            "clearedCount": result["clearedCount"],
        }

    if action == "runSelfTestSuite":
        result = _run_self_test_suite(data)
        return _ok_data(
            totalCount=result["totalCount"],
            passedCount=result["passedCount"],
            failedCount=result["failedCount"],
            results=result["results"],
        )

    return {"ok": False, "message": f"Unknown action: {action}", "errorCode": ERROR_CONTRACT, "state": None}


def _push_parameter_list():
    _send_to_palette("renderState", _ok_state(_current_state_payload()))


def _send_to_palette(action, payload):
    palette = _palette()
    if palette:
        palette.sendInfoToHTML(action, json.dumps(payload))


def _current_state_payload(settings=None):
    active_settings = settings if settings is not None else _load_settings()
    design = _design()
    order_state = _sync_ui_state_between_local_and_fusion(design, _read_document_order_state()) if design else _read_document_order_state()
    parameters = _collect_user_parameters(order_state)
    return {
        "ok": True,
        "apiVersion": 1,
        "parameters": parameters,
        "groups": _collect_parameter_groups(parameters),
        "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
        "parameterNames": _collect_all_parameter_names(),
        "settings": active_settings,
        "document": _active_document_info(),
        "documentDefaults": {
            "unit": _default_document_unit(),
        },
        "modelParameterCount": _model_parameter_count(),
        "textTunerState": _load_text_tuner_state(),
        "fusionTheme": _detect_fusion_theme(),
        "updateInfo": _build_update_info_payload(active_settings),
    }


def _build_update_info_payload(settings=None):
    current_version = _current_addin_version()
    update_state = _current_update_state()
    if settings is None:
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


def _collect_user_parameters(order_state=None):
    design = _design()
    if not design:
        return []

    units_manager = design.unitsManager
    if order_state is None:
        order_state = _sync_ui_state_between_local_and_fusion(design, _read_document_order_state())
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
        fusion_payload = _parameter_metadata_payload(param)
        json_payload = _normalized_metadata_payload(
            group_name=saved_record.get("group") or "",
            metadata_changed_at=saved_record.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=saved_record.get(METADATA_REVISION_RECORD_KEY),
            writer_id=saved_record.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=saved_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )
        latest_payload = _choose_latest_metadata(fusion_payload, json_payload)
        backfill_attributes_from_saved = _is_metadata_newer(json_payload, fusion_payload)
        if backfill_attributes_from_saved:
            _write_parameter_group_name(param, latest_payload.get("group") or "", latest_payload.get(METADATA_CHANGED_AT_RECORD_KEY), latest_payload)

        results.append(
            {
                "key": parameter_key,
                "name": param.name,
                "expression": param.expression,
                "unit": param.unit,
                "comment": param.comment or "",
                "isFavorite": param.isFavorite,
                "group": latest_payload.get("group") or "",
                "valuePreview": _format_parameter_value(param, units_manager),
                "previousExpression": str(saved_record.get("previous_expression") or ""),
                "previousValue": str(saved_record.get("previous_value") or ""),
                "metadataChangedAt": _metadata_changed_at_value(latest_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
                "metadataRevision": _metadata_revision_value(latest_payload.get(METADATA_REVISION_RECORD_KEY)),
                "metadataWriterId": _metadata_writer_id_value(latest_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
                "metadataWriterVersion": _metadata_writer_version_value(latest_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
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


def _created_by_label(param):
    """Return human-readable name of the Fusion object that created this parameter, or ''."""
    try:
        creator = param.createdBy
        if not creator:
            return ""
        name = getattr(creator, "name", None)
        return str(name) if name else ""
    except Exception:
        return ""


def _find_model_parameter_by_token(design, token):
    if not design or not token:
        return None
    try:
        found = design.findEntityByToken(token)
    except Exception:
        return None

    # findEntityByToken returns an ObjectCollection, not a list/tuple.
    # Try iterating regardless of concrete type.
    try:
        for item in found:
            param = adsk.fusion.ModelParameter.cast(item)
            if param:
                return param
    except Exception:
        pass
    return None


_MODEL_PARAMETER_MAX_LIMIT = 1000  # hard cap per page


def _model_parameter_count():
    """Return the total number of model parameters across all components in the active design.

    Iterates design.allComponents and sums each component's modelParameters.count.
    Returns 0 if no design is active or the collection is inaccessible.
    """
    design = _design()
    if not design:
        return 0
    try:
        total = 0
        all_comps = design.allComponents
        for i in range(all_comps.count):
            comp = all_comps.item(i)
            if comp:
                total += comp.modelParameters.count
        return total
    except Exception:
        return 0


def _serialize_model_parameter(param, units_manager, component_name=""):
    """Return the serialized dict for a single ModelParameter.

    component_name: display name of the owning component. Empty string for root.
    """
    return {
        "key": _parameter_entity_token(param),
        "name": param.name,
        "expression": param.expression,
        "unit": param.unit,
        "comment": param.comment or "",
        "isFavorite": param.isFavorite,
        "valuePreview": _format_parameter_value(param, units_manager),
        "isDeletable": False,
        "createdBy": _created_by_label(param),
        "componentName": component_name,
    }


def _get_model_parameters(data):
    """Return a paginated, optionally filtered list of model parameters.

    Pagination:
        offset  int  First item index (0-based). Default 0.
        limit   int  Max items to return. Default 200. Hard cap: 1000.

    Filtering:
        filter  str  Case-insensitive substring filter applied to name and
                     expression. Empty / absent = return all.

    Sort: case-insensitive by name (stable, applied after filter, before slice).

    Returns dict with: ok, totalCount, parameters, offset, limit.
        totalCount  Total items matching the filter (not the page size).
        parameters  Serialized items for the requested page.

    Never raises — requires an active design (raises BPNoDesignError).
    """
    design = _require_design()

    raw_offset = data.get("offset")
    raw_limit = data.get("limit")
    filter_str = str(data.get("filter") or "").strip().casefold()

    offset = max(0, int(raw_offset)) if raw_offset is not None else 0
    limit = max(1, min(int(raw_limit), _MODEL_PARAMETER_MAX_LIMIT)) if raw_limit is not None else 200

    units_manager = design.unitsManager

    try:
        all_comps = design.allComponents
    except Exception:
        return {"ok": True, "totalCount": 0, "parameters": [], "offset": offset, "limit": limit}

    # Collect from all components — (param, component_name) tuples.
    # Linear scan across all components is unavoidable for arbitrary filter text.
    candidates = []
    for comp_idx in range(all_comps.count):
        comp = all_comps.item(comp_idx)
        if not comp:
            continue
        comp_name = comp.name or ""
        try:
            param_collection = comp.modelParameters
        except Exception:
            continue
        for idx in range(param_collection.count):
            param = param_collection.item(idx)
            if not param:
                continue
            if filter_str:
                name_cf = (param.name or "").casefold()
                expr_cf = (param.expression or "").casefold()
                comp_cf = comp_name.casefold()
                if filter_str not in name_cf and filter_str not in expr_cf and filter_str not in comp_cf:
                    continue
            candidates.append((param, comp_name))

    # Sort by component name then parameter name, both case-insensitive.
    candidates.sort(key=lambda t: (t[1].casefold(), (t[0].name or "").casefold()))
    filtered_count = len(candidates)

    page = candidates[offset: offset + limit]
    results = [_serialize_model_parameter(p, units_manager, comp_name) for p, comp_name in page]

    return {
        "ok": True,
        "totalCount": filtered_count,
        "parameters": results,
        "offset": offset,
        "limit": limit,
    }


def _settings_path():
    return Path(__file__).resolve().with_name(SETTINGS_FILE)


def _text_tuner_state_path():
    root = _app_support_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / TEXT_TUNER_STATE_FILE


def _normalize_text_tuner_state(values):
    if not isinstance(values, dict):
        return {}

    normalized = {}
    for raw_key, raw_value in values.items():
        if not isinstance(raw_key, str):
            continue
        key = raw_key.strip()
        if not key or len(key) > 80:
            continue

        if raw_value is None:
            continue
        text = str(raw_value).strip()
        if not text:
            continue
        if len(text) > 300:
            text = text[:300]
        normalized[key] = text
        if len(normalized) >= 200:
            break
    return normalized


def _load_text_tuner_state():
    path = _text_tuner_state_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return _normalize_text_tuner_state(loaded)


def _save_text_tuner_state(values):
    normalized = _normalize_text_tuner_state(values)
    path = _text_tuner_state_path()
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return normalized


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
        "groupUi": {
            "order": [],
            "collapsed": {},
        },
        UI_STATE_RECORD_KEY: {
            UI_STATE_REVISION_KEY: 0,
            UI_STATE_CHANGED_AT_KEY: 0,
            UI_STATE_WRITER_ID_KEY: "",
            UI_STATE_WRITER_VERSION_KEY: "",
        },
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
                METADATA_REVISION_RECORD_KEY: _metadata_revision_value(record.get(METADATA_REVISION_RECORD_KEY)),
                METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(record.get(METADATA_WRITER_ID_RECORD_KEY)),
                METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(record.get(METADATA_WRITER_VERSION_RECORD_KEY)),
            }

    state["documentId"] = str(loaded.get("documentId") or state["documentId"])
    state["documentName"] = str(loaded.get("documentName") or state["documentName"])
    state["parameters"] = records
    state["groupUi"] = _normalized_group_ui_state(loaded.get("groupUi"))
    state[UI_STATE_RECORD_KEY] = _normalized_ui_state_record(loaded.get(UI_STATE_RECORD_KEY))
    return state


def _write_document_order_state(state):
    info = _active_document_info()
    document_id = state.get("documentId") if isinstance(state, dict) else ""
    document_name = state.get("documentName") if isinstance(state, dict) else ""
    document_id = str(document_id or info.get("id", ""))
    document_name = str(document_name or info.get("name", ""))
    path = _document_order_path(document_id, document_name)
    normalized_parameters = {}
    source_parameters = state.get("parameters", {}) if isinstance(state, dict) else {}
    if isinstance(source_parameters, dict):
        for token, record in source_parameters.items():
            if not isinstance(token, str) or not token:
                continue
            if not isinstance(record, dict):
                continue
            order_value = record.get("order")
            if not isinstance(order_value, int):
                continue
            normalized_parameters[token] = {
                "order": order_value,
                "name": str(record.get("name") or ""),
                "current_expression": str(record.get("current_expression") or ""),
                "previous_expression": str(record.get("previous_expression") or ""),
                "current_value": str(record.get("current_value") or ""),
                "previous_value": str(record.get("previous_value") or ""),
                "group": _normalize_group_name(record.get("group") or ""),
                METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(record.get(METADATA_CHANGED_AT_RECORD_KEY)),
                METADATA_REVISION_RECORD_KEY: _metadata_revision_value(record.get(METADATA_REVISION_RECORD_KEY)),
                METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(record.get(METADATA_WRITER_ID_RECORD_KEY)),
                METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(record.get(METADATA_WRITER_VERSION_RECORD_KEY)),
            }

    payload = {
        "documentId": document_id,
        "documentName": document_name,
        "parameters": normalized_parameters,
        "groupUi": _normalized_group_ui_state(state.get("groupUi") if isinstance(state, dict) else {}),
        UI_STATE_RECORD_KEY: _normalized_ui_state_record(state.get(UI_STATE_RECORD_KEY) if isinstance(state, dict) else {}),
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

    # findEntityByToken returns an ObjectCollection, not a list/tuple.
    # Try iterating regardless of concrete type.
    try:
        for item in found:
            parameter = adsk.fusion.UserParameter.cast(item)
            if parameter:
                return parameter
    except Exception:
        pass

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
            METADATA_REVISION_RECORD_KEY: _metadata_revision_value(record.get(METADATA_REVISION_RECORD_KEY)),
            METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(record.get(METADATA_WRITER_ID_RECORD_KEY)),
            METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(record.get(METADATA_WRITER_VERSION_RECORD_KEY)),
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
        previous_metadata_revision = _metadata_revision_value(previous_record.get(METADATA_REVISION_RECORD_KEY))
        previous_metadata_writer_id = _metadata_writer_id_value(previous_record.get(METADATA_WRITER_ID_RECORD_KEY))
        previous_metadata_writer_version = _metadata_writer_version_value(previous_record.get(METADATA_WRITER_VERSION_RECORD_KEY))
        old_current_expression = str(previous_record.get("current_expression") or "")
        old_current_value = str(previous_record.get("current_value") or "")
        incoming_group = _normalize_group_name(parameter.get("group") or previous_group)
        incoming_metadata_changed_at = _metadata_changed_at_value(parameter.get("metadataChangedAt"))
        incoming_metadata_revision = _metadata_revision_value(parameter.get("metadataRevision"))
        incoming_metadata_writer_id = _metadata_writer_id_value(parameter.get("metadataWriterId"))
        incoming_metadata_writer_version = _metadata_writer_version_value(parameter.get("metadataWriterVersion"))

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
            metadata_revision = max(previous_metadata_revision + 1, incoming_metadata_revision, 1)
            metadata_writer_id = _current_writer_id()
            metadata_writer_version = _current_writer_version()
        else:
            metadata_changed_at = max(previous_metadata_changed_at, incoming_metadata_changed_at)
            if metadata_changed_at <= 0:
                metadata_changed_at = _now_metadata_timestamp_ms()
            metadata_revision = max(previous_metadata_revision, incoming_metadata_revision, 1)
            metadata_writer_id = incoming_metadata_writer_id or previous_metadata_writer_id or _current_writer_id()
            metadata_writer_version = incoming_metadata_writer_version or previous_metadata_writer_version or _current_writer_version()

        records[key] = {
            "order": index,
            "name": str(parameter.get("name") or ""),
            "current_expression": incoming_expression,
            "previous_expression": previous_expression,
            "current_value": incoming_value,
            "previous_value": previous_value,
            "group": incoming_group,
            METADATA_CHANGED_AT_RECORD_KEY: metadata_changed_at,
            METADATA_REVISION_RECORD_KEY: metadata_revision,
            METADATA_WRITER_ID_RECORD_KEY: metadata_writer_id,
            METADATA_WRITER_VERSION_RECORD_KEY: metadata_writer_version,
        }
        if touch_attribute_timestamp and design:
            parameter_entity = _find_user_parameter_by_token(design, key)
            if parameter_entity:
                _set_parameter_metadata_changed_at(parameter_entity, metadata_changed_at)

    next_state = {
        "documentId": info.get("id", ""),
        "documentName": info.get("name", ""),
        "parameters": records,
        "groupUi": _normalized_group_ui_state((previous_state or {}).get("groupUi") if isinstance(previous_state, dict) else {}),
        UI_STATE_RECORD_KEY: _normalized_ui_state_record((previous_state or {}).get(UI_STATE_RECORD_KEY) if isinstance(previous_state, dict) else {}),
    }
    if previous_state == next_state:
        return
    _write_document_order_state(next_state)


def _load_settings():
    settings = dict(DEFAULT_SETTINGS)
    settings["paletteSize"] = dict(DEFAULT_SETTINGS["paletteSize"])
    settings["palettePosition"] = {}
    settings["parameterTableColumns"] = dict(DEFAULT_SETTINGS["parameterTableColumns"])
    settings["unitCategoryState"] = dict(DEFAULT_SETTINGS["unitCategoryState"])
    settings["customUnits"] = []
    settings["showRevertButtons"] = bool(DEFAULT_SETTINGS["showRevertButtons"])
    settings["showCommentColumn"] = bool(DEFAULT_SETTINGS["showCommentColumn"])
    settings["showTextTunerSidebar"] = bool(DEFAULT_SETTINGS["showTextTunerSidebar"])
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
        if isinstance(loaded.get("palettePosition"), dict):
            x = loaded["palettePosition"].get("x")
            y = loaded["palettePosition"].get("y")
            if isinstance(x, int) and isinstance(y, int):
                settings["palettePosition"] = {"x": x, "y": y}
        palette_docking_state = loaded.get("paletteDockingState")
        if isinstance(palette_docking_state, str):
            normalized_docking_state = palette_docking_state.strip().lower()
            if normalized_docking_state in ALLOWED_PALETTE_DOCKING_STATE_NAMES:
                settings["paletteDockingState"] = normalized_docking_state
        if isinstance(loaded.get("parameterTableColumns"), dict):
            stored_cols = loaded["parameterTableColumns"]
            for key in DEFAULT_SETTINGS["parameterTableColumns"]:
                # Try new key name first; fall back to old key name for settings files
                # written before the column key rename (parameter/name/unit/expression/value).
                incoming_value = stored_cols.get(key)
                if incoming_value is None:
                    old_key = _COLUMN_KEY_OLD_NAMES.get(key)
                    if old_key:
                        incoming_value = stored_cols.get(old_key)
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

        if isinstance(loaded.get("showCommentColumn"), bool):
            settings["showCommentColumn"] = loaded["showCommentColumn"]

        if isinstance(loaded.get("showTextTunerSidebar"), bool):
            settings["showTextTunerSidebar"] = loaded["showTextTunerSidebar"]

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

        if isinstance(loaded.get("autoOpenOnStart"), bool):
            settings["autoOpenOnStart"] = loaded["autoOpenOnStart"]

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

    palette_position = data.get("palettePosition")
    if palette_position is not None:
        if not isinstance(palette_position, dict):
            raise ValueError('"palettePosition" must be an object.')

        x = palette_position.get("x")
        y = palette_position.get("y")
        if x is not None and not isinstance(x, int):
            raise ValueError('"palettePosition.x" must be an integer.')
        if y is not None and not isinstance(y, int):
            raise ValueError('"palettePosition.y" must be an integer.')
        if isinstance(x, int) and isinstance(y, int):
            settings["palettePosition"] = {"x": x, "y": y}

    palette_docking_state = data.get("paletteDockingState")
    if palette_docking_state is not None:
        if not isinstance(palette_docking_state, str):
            raise ValueError('"paletteDockingState" must be a string.')
        normalized_docking_state = palette_docking_state.strip().lower()
        if normalized_docking_state not in ALLOWED_PALETTE_DOCKING_STATE_NAMES:
            raise ValueError('"paletteDockingState" must be one of: floating, left, right, top, bottom.')
        settings["paletteDockingState"] = normalized_docking_state

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

        settings["parameterTableColumns"] = normalized

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

    if "showCommentColumn" in data:
        show_comment_column = data.get("showCommentColumn")
        if not isinstance(show_comment_column, bool):
            raise ValueError('"showCommentColumn" must be a boolean.')
        settings["showCommentColumn"] = show_comment_column

    if "showTextTunerSidebar" in data:
        show_text_tuner_sidebar = data.get("showTextTunerSidebar")
        if not isinstance(show_text_tuner_sidebar, bool):
            raise ValueError('"showTextTunerSidebar" must be a boolean.')
        settings["showTextTunerSidebar"] = show_text_tuner_sidebar

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

    if "autoOpenOnStart" in data:
        auto_open = data.get("autoOpenOnStart")
        if not isinstance(auto_open, bool):
            raise ValueError('"autoOpenOnStart" must be a boolean.')
        settings["autoOpenOnStart"] = auto_open

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


def _detect_fusion_theme():
    if not app:
        return "light"
    try:
        prefs = app.preferences.generalPreferences
        theme = prefs.activeUserInterfaceTheme
        if theme == adsk.core.UserInterfaceThemes.DarkUserInterfaceTheme:
            return "dark"
        return "light"
    except Exception:
        return "light"


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


def _palette_docking_state_name_map():
    docking_states = getattr(adsk.core, "PaletteDockingStates", None)
    if docking_states is None:
        return {}

    mapping = {}
    candidates = [
        ("floating", "PaletteDockStateFloating"),
        ("left", "PaletteDockStateLeft"),
        ("right", "PaletteDockStateRight"),
        ("top", "PaletteDockStateTop"),
        ("bottom", "PaletteDockStateBottom"),
    ]
    for name, attr_name in candidates:
        value = getattr(docking_states, attr_name, None)
        if value is not None:
            mapping[name] = value
    return mapping


def _palette_docking_state_to_name(docking_state):
    mapping = _palette_docking_state_name_map()
    for name, value in mapping.items():
        if docking_state == value:
            return name
    return "floating"


def _is_palette_floating(palette):
    mapping = _palette_docking_state_name_map()
    floating_state = mapping.get("floating")
    if floating_state is None:
        return True
    try:
        return palette.dockingState == floating_state
    except Exception:
        return True


def _apply_saved_palette_docking_state(palette):
    settings = _load_settings()
    requested = str(settings.get("paletteDockingState") or "floating").strip().lower()
    if requested not in ALLOWED_PALETTE_DOCKING_STATE_NAMES:
        requested = "floating"

    mapping = _palette_docking_state_name_map()
    target_state = mapping.get(requested) or mapping.get("floating")
    if target_state is None:
        return

    try:
        palette.dockingState = target_state
    except Exception:
        if app:
            app.log(f"Better Parameters palette docking restore failed:\n{traceback.format_exc()}")


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


def _apply_saved_palette_position(palette):
    if not _is_palette_floating(palette):
        return

    settings = _load_settings()
    position = settings.get("palettePosition") or {}
    x = position.get("x")
    y = position.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        return

    try:
        palette.left = x
        palette.top = y
    except Exception:
        if app:
            app.log(f"Better Parameters palette position restore failed:\n{traceback.format_exc()}")


def _save_palette_geometry(palette):
    payload = {"paletteSize": {}, "palettePosition": {}}

    try:
        payload["paletteDockingState"] = _palette_docking_state_to_name(palette.dockingState)
    except Exception:
        payload["paletteDockingState"] = "floating"

    try:
        width = int(palette.width)
        if width >= 320:
            payload["paletteSize"]["width"] = width
    except Exception:
        pass

    try:
        height = int(palette.height)
        if height >= 240:
            payload["paletteSize"]["height"] = height
    except Exception:
        pass

    if _is_palette_floating(palette):
        try:
            payload["palettePosition"]["x"] = int(palette.left)
            payload["palettePosition"]["y"] = int(palette.top)
        except Exception:
            payload["palettePosition"] = {}
    else:
        payload["palettePosition"] = {}

    if not payload["paletteSize"]:
        payload.pop("paletteSize")
    if not payload["palettePosition"]:
        payload.pop("palettePosition")
    if not payload:
        return

    _save_settings(payload)


def _update_parameter(data):
    design = _require_design()
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    if not key and not name:
        raise ValueError('Either "key" or "name" is required.')

    expression = _required_text(data, "expression")
    comment = data.get("comment", "")

    parameter = _find_user_parameter_by_token(design, key) if key else None
    if not parameter and name:
        parameter = design.userParameters.itemByName(name)
    if not parameter:
        raise ValueError("User parameter was not found.")

    parameter.expression = expression
    parameter.comment = comment


def _batch_update_parameters(data):
    """Apply multiple user parameter expression/comment updates in one Fusion call.

    Uses design.modifyParameters() when available (Fusion API Sept 2022+) to apply
    all expression changes in a single call, triggering only one design recomputation.
    Falls back to sequential .expression= assignments on older Fusion builds.

    Comments are applied after expressions; comment writes do not trigger recomputation.

    Returns dict with keys: ok, updatedCount, failedRows, message.
    Raises BPNoDesignError if no design is active.
    Raises BPValidationError if "updates" is missing or not a list.
    """
    design = _require_design()
    updates = data.get("updates")
    if not isinstance(updates, list):
        raise BPValidationError('"updates" must be an array.')
    if not updates:
        return {"ok": True, "updatedCount": 0, "failedRows": [], "message": ""}

    # --- Phase 1: resolve all parameters and build Fusion input arrays -------
    params_list = []
    values_list = []
    comment_pairs = []   # (param, comment_str_or_None)
    failed_rows = []

    for record in updates:
        rec_key  = str(record.get("key")  or "").strip()
        rec_name = str(record.get("name") or "").strip()
        expression = str(record.get("expression") or "").strip()
        comment = record.get("comment")           # None means "don't touch comment"

        param = _find_user_parameter_by_token(design, rec_key) if rec_key else None
        if not param and rec_name:
            param = design.userParameters.itemByName(rec_name)
        if not param:
            failed_rows.append({
                "name": rec_name or rec_key,
                "message": "Parameter not found.",
            })
            continue

        try:
            value_input = adsk.core.ValueInput.createByString(expression)
        except Exception as exc:
            failed_rows.append({"name": param.name, "message": str(exc)})
            continue

        params_list.append(param)
        values_list.append(value_input)
        comment_pairs.append((param, comment))

    if failed_rows:
        return {
            "ok": False,
            "errorCode": ERROR_NOT_FOUND,
            "message": f"{len(failed_rows)} parameter(s) not found.",
            "updatedCount": 0,
            "failedRows": failed_rows,
        }

    # --- Phase 2: apply all expressions — single Fusion recompute -----------
    if hasattr(design, "modifyParameters"):
        # Preferred path: one Fusion call → one design recompute cycle.
        try:
            success = design.modifyParameters(params_list, values_list)
        except Exception as exc:
            return {
                "ok": False,
                "errorCode": ERROR_UNKNOWN,
                "message": f"modifyParameters failed: {exc}",
                "updatedCount": 0,
                "failedRows": [],
            }
        if not success:
            return {
                "ok": False,
                "errorCode": ERROR_VALIDATION,
                "message": "modifyParameters returned False — one or more expressions may be invalid.",
                "updatedCount": 0,
                "failedRows": [],
            }
    else:
        # Fallback: sequential .expression= for Fusion builds < Sept 2022.
        sequential_failed = []
        for param, value_input in zip(params_list, values_list):
            try:
                param.expression = str(value_input)
            except Exception as exc:
                sequential_failed.append({"name": param.name, "message": str(exc)})
        if sequential_failed:
            return {
                "ok": False,
                "errorCode": ERROR_VALIDATION,
                "message": f"{len(sequential_failed)} expression(s) rejected by Fusion.",
                "updatedCount": len(params_list) - len(sequential_failed),
                "failedRows": sequential_failed,
            }

    # --- Phase 3: apply comments (no recompute triggered) --------------------
    for param, comment in comment_pairs:
        if comment is not None:
            try:
                param.comment = str(comment)
            except Exception:
                pass  # comment failure is non-fatal

    return {
        "ok": True,
        "updatedCount": len(params_list),
        "failedRows": [],
        "message": "",
    }


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
    previous_payload = _normalized_metadata_payload(
        group_name=record.get("group") or _parameter_group_name(parameter) or "",
        metadata_changed_at=record.get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=record.get(METADATA_REVISION_RECORD_KEY),
        writer_id=record.get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=record.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    next_payload = _next_metadata_payload(previous_payload, previous_payload.get("group") or "", _now_metadata_timestamp_ms())
    metadata_changed_at = _metadata_changed_at_value(next_payload.get(METADATA_CHANGED_AT_RECORD_KEY))

    stored_records[parameter_key] = {
        "order": order_value,
        "name": str(parameter.name or ""),
        "current_expression": str(parameter.expression or ""),
        "previous_expression": current_expression,
        "current_value": reverted_value,
        "previous_value": current_value,
        "group": _normalize_group_name(next_payload.get("group") or ""),
        METADATA_CHANGED_AT_RECORD_KEY: metadata_changed_at,
        METADATA_REVISION_RECORD_KEY: _metadata_revision_value(next_payload.get(METADATA_REVISION_RECORD_KEY)),
        METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(next_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
        METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
    }
    _write_parameter_group_name(parameter, next_payload.get("group") or "", metadata_changed_at, next_payload)
    _write_document_order_state(
        {
            "documentId": order_state.get("documentId", ""),
            "documentName": order_state.get("documentName", ""),
            "parameters": stored_records,
            "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
            UI_STATE_RECORD_KEY: _normalized_ui_state_record(order_state.get(UI_STATE_RECORD_KEY)),
        }
    )


def _set_parameter_favorite(data):
    design = _require_design()
    name = _required_text(data, "name")
    is_favorite = bool(data.get("isFavorite"))

    param = design.allParameters.itemByName(name)
    if not param:
        raise ValueError(f'Parameter "{name}" was not found.')

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
    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    parameter_key = _parameter_entity_token(parameter)
    existing_record = records.get(parameter_key) if isinstance(records.get(parameter_key), dict) else {}
    previous_payload = _choose_latest_metadata(
        _parameter_metadata_payload(parameter),
        _normalized_metadata_payload(
            group_name=existing_record.get("group") or "",
            metadata_changed_at=existing_record.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=existing_record.get(METADATA_REVISION_RECORD_KEY),
            writer_id=existing_record.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=existing_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
        ),
    )
    next_payload = _next_metadata_payload(previous_payload, group_name, _now_metadata_timestamp_ms())
    _write_parameter_group_name(parameter, group_name, next_payload.get(METADATA_CHANGED_AT_RECORD_KEY), next_payload)
    _set_parameter_group_record(
        design,
        parameter,
        group_name,
        next_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
        next_payload.get(METADATA_REVISION_RECORD_KEY),
        next_payload.get(METADATA_WRITER_ID_RECORD_KEY),
        next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )


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
    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue
        existing_group = _parameter_group_name(parameter)
        if not existing_group:
            existing_group = _parameter_group_from_record(design, parameter)
        if existing_group.casefold() != old_group.casefold():
            continue
        parameter_key = _parameter_entity_token(parameter)
        existing_record = records.get(parameter_key) if isinstance(records.get(parameter_key), dict) else {}
        previous_payload = _choose_latest_metadata(
            _parameter_metadata_payload(parameter),
            _normalized_metadata_payload(
                group_name=existing_record.get("group") or "",
                metadata_changed_at=existing_record.get(METADATA_CHANGED_AT_RECORD_KEY),
                revision=existing_record.get(METADATA_REVISION_RECORD_KEY),
                writer_id=existing_record.get(METADATA_WRITER_ID_RECORD_KEY),
                writer_version=existing_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
            ),
        )
        next_payload = _next_metadata_payload(previous_payload, new_group, metadata_changed_at)
        _write_parameter_group_name(parameter, new_group, next_payload.get(METADATA_CHANGED_AT_RECORD_KEY), next_payload)
        _set_parameter_group_record(
            design,
            parameter,
            new_group,
            next_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
            next_payload.get(METADATA_REVISION_RECORD_KEY),
            next_payload.get(METADATA_WRITER_ID_RECORD_KEY),
            next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )


def _delete_group(data):
    design = _require_design()
    group_name = _normalize_group_name(_required_text(data, "group"))
    if not group_name:
        raise ValueError("Ungrouped cannot be deleted.")

    params = design.userParameters
    metadata_changed_at = _now_metadata_timestamp_ms()
    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue
        existing_group = _parameter_group_name(parameter)
        if not existing_group:
            existing_group = _parameter_group_from_record(design, parameter)
        if existing_group.casefold() != group_name.casefold():
            continue
        parameter_key = _parameter_entity_token(parameter)
        existing_record = records.get(parameter_key) if isinstance(records.get(parameter_key), dict) else {}
        previous_payload = _choose_latest_metadata(
            _parameter_metadata_payload(parameter),
            _normalized_metadata_payload(
                group_name=existing_record.get("group") or "",
                metadata_changed_at=existing_record.get(METADATA_CHANGED_AT_RECORD_KEY),
                revision=existing_record.get(METADATA_REVISION_RECORD_KEY),
                writer_id=existing_record.get(METADATA_WRITER_ID_RECORD_KEY),
                writer_version=existing_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
            ),
        )
        next_payload = _next_metadata_payload(previous_payload, "", metadata_changed_at)
        _write_parameter_group_name(parameter, "", next_payload.get(METADATA_CHANGED_AT_RECORD_KEY), next_payload)
        _set_parameter_group_record(
            design,
            parameter,
            "",
            next_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
            next_payload.get(METADATA_REVISION_RECORD_KEY),
            next_payload.get(METADATA_WRITER_ID_RECORD_KEY),
            next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )


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

    group_filter = _normalize_group_name(data["group"]) if "group" in data else None
    previous_state = _read_document_order_state()

    if group_filter is None:
        # Flat global reorder (original behaviour): keys describes the full cross-group order.
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
        merged.extend(p for p in current_parameters if p.get("key") in current_by_key)
    else:
        # Per-group reorder: only reorders parameters within the specified group;
        # all other groups' relative order is preserved.
        records = _resolve_document_order_records(design, previous_state.get("parameters") or {})
        params = design.userParameters

        all_params = []
        for index in range(params.count):
            param = params.item(index)
            if not param:
                continue
            key = _parameter_entity_token(param)
            record = records.get(key) or {}
            param_group = _normalize_group_name(record.get("group") or _parameter_group_name(param) or "")
            sort_order = record.get("order") if isinstance(record.get("order"), int) else params.count + index
            all_params.append({
                "key": key,
                "name": param.name,
                "group": param_group,
                "_sort": sort_order,
            })
        all_params.sort(key=lambda x: x["_sort"])

        # Build new order for the target group.
        in_group = {p["key"]: p for p in all_params if p["group"].casefold() == group_filter.casefold()}
        new_group_order = []
        for key in ordered_keys:
            item = in_group.pop(key, None)
            if item:
                new_group_order.append(item)
        # Append group members not mentioned in keys (preserve their relative order).
        for p in all_params:
            if p["key"] in in_group:
                new_group_order.append(p)

        # Splice reordered group members back into the full list at the original group slots.
        group_iter = iter(new_group_order)
        merged = []
        for p in all_params:
            if p["group"].casefold() == group_filter.casefold():
                try:
                    merged.append(next(group_iter))
                except StopIteration:
                    pass
            else:
                merged.append(p)

    _persist_document_order_snapshot(merged, previous_state)
    next_state = _read_document_order_state()
    next_state[UI_STATE_RECORD_KEY] = _bump_ui_state_record(next_state.get(UI_STATE_RECORD_KEY))
    _write_document_order_state(next_state)
    _write_fusion_ui_snapshot(design, _local_ui_snapshot(next_state))


def _save_group_ui_state(data):
    design = _require_design()
    order_state = _read_document_order_state()
    next_group_ui = _normalized_group_ui_state(data.get("groupUi") if isinstance(data, dict) else {})
    if order_state.get("groupUi") == next_group_ui:
        return
    ui_state = _bump_ui_state_record(order_state.get(UI_STATE_RECORD_KEY))
    _write_document_order_state(
        {
            "documentId": order_state.get("documentId", ""),
            "documentName": order_state.get("documentName", ""),
            "parameters": order_state.get("parameters", {}),
            "groupUi": next_group_ui,
            UI_STATE_RECORD_KEY: ui_state,
        }
    )
    _write_fusion_ui_snapshot(design, _local_ui_snapshot(_read_document_order_state()))


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


def _delete_parameter(data):
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

    try:
        parameter.deleteMe()
    except Exception as exc:
        raise ValueError(f"Fusion could not delete this parameter: {exc}")


def _rename_parameter(data):
    design = _require_design()
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    if not key and not name:
        raise ValueError('Either "key" or "name" is required.')
    new_name = _required_text(data, "newName")

    parameter = _find_user_parameter_by_token(design, key) if key else None
    if not parameter and name:
        parameter = design.userParameters.itemByName(name)
    if not parameter:
        raise ValueError("User parameter was not found.")

    validation = _validate_parameter_name_response(new_name)
    if not validation["ok"]:
        raise ValueError(validation["message"])

    try:
        parameter.name = new_name
    except Exception as exc:
        raise ValueError(f"Fusion could not rename this parameter: {exc}")


def _update_model_parameter(data):
    design = _require_design()
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    if not key and not name:
        raise ValueError('Either "key" or "name" is required.')

    expression = _required_text(data, "expression")

    parameter = _find_model_parameter_by_token(design, key) if key else None
    if not parameter and name:
        # Search all components — root-only lookup misses subcomponent params.
        # Returns first match; key (entityToken) should be preferred for unambiguous lookup.
        try:
            all_comps = design.allComponents
            for _ci in range(all_comps.count):
                _comp = all_comps.item(_ci)
                if not _comp:
                    continue
                try:
                    _p = _comp.modelParameters.itemByName(name)
                    if _p:
                        parameter = _p
                        break
                except Exception:
                    continue
        except Exception:
            pass
    if not parameter:
        raise ValueError("Model parameter was not found.")

    expr_result = _validate_expression_response(expression, parameter.name, parameter.unit)
    if not expr_result["ok"] and not expr_result.get("isIncomplete"):
        raise ValueError(expr_result["message"])

    try:
        parameter.expression = expression
    except Exception as exc:
        raise ValueError(f"Fusion could not update model parameter '{parameter.name}': {exc}")

    if "comment" in data:
        try:
            parameter.comment = str(data.get("comment") or "")
        except Exception:
            pass


def _validate_unit_change_response(data):
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    new_unit = str(data.get("newUnit") or "").strip()
    new_expression = str(data.get("newExpression") or "").strip()

    if not key and not name:
        return {"ok": False, "message": 'Either "key" or "name" is required.', "isIncomplete": False, "preview": ""}
    if not new_expression:
        return {"ok": False, "message": '"newExpression" is required.', "isIncomplete": False, "preview": ""}

    unit_result = _validate_unit_response(new_unit)
    if not unit_result["ok"]:
        return {"ok": False, "message": unit_result["message"], "isIncomplete": False, "preview": ""}
    normalized_unit = unit_result["unit"]

    param_name = ""
    design = _design()
    if design:
        param = _find_user_parameter_by_token(design, key) if key else None
        if not param and name:
            param = design.userParameters.itemByName(name)
        if param:
            param_name = str(param.name or "")

    expr_result = _validate_expression_response(new_expression, param_name, normalized_unit)
    if not expr_result["ok"]:
        return {**expr_result, "preview": ""}

    preview_result = _preview_expression_response(new_expression, param_name, normalized_unit, "")
    return {
        "ok": True,
        "message": "",
        "isIncomplete": False,
        "preview": preview_result.get("preview", ""),
    }


def _update_parameter_unit(data):
    """Change the unit of an existing parameter.

    Fusion's UserParameter.unit is read-only. The only way to change unit is
    delete and recreate. This means the entity token (key) changes. The new
    key is returned as the 'newKey' extra field on the action response so the
    FE can update its reference.

    Fails with a clear error if the parameter is referenced by model features
    or other parameters (Fusion will reject the deletion).
    """
    design = _require_design()
    key = str(data.get("key") or "").strip()
    name = str(data.get("name") or "").strip()
    if not key and not name:
        raise ValueError('Either "key" or "name" is required.')
    new_expression = _required_text(data, "newExpression")
    new_unit = str(data.get("newUnit") or "").strip()
    comment_override = data.get("comment")

    parameter = _find_user_parameter_by_token(design, key) if key else None
    if not parameter and name:
        parameter = design.userParameters.itemByName(name)
    if not parameter:
        raise ValueError("User parameter was not found.")

    unit_result = _validate_unit_response(new_unit)
    if not unit_result["ok"]:
        raise ValueError(unit_result["message"])
    normalized_unit = unit_result["unit"]

    expr_result = _validate_expression_response(new_expression, str(parameter.name or ""), normalized_unit)
    if not expr_result["ok"]:
        raise ValueError(expr_result["message"])

    # Capture all state before deletion.
    param_name = str(parameter.name or "")
    param_comment = str(comment_override if comment_override is not None else (parameter.comment or ""))
    param_favorite = bool(parameter.isFavorite)
    old_token = _parameter_entity_token(parameter)

    order_state = _read_document_order_state()
    stored_records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    old_record = stored_records.get(old_token) or {}
    old_group = _normalize_group_name(old_record.get("group") or _parameter_group_name(parameter) or "")
    old_order = old_record.get("order")
    if not isinstance(old_order, int):
        old_order = len(stored_records)

    try:
        parameter.deleteMe()
    except Exception as exc:
        raise ValueError(f"Fusion could not change unit for '{param_name}' because it is in use: {exc}")

    value_input = adsk.core.ValueInput.createByString(new_expression)
    created = design.userParameters.add(param_name, value_input, normalized_unit, param_comment)
    if not created:
        raise ValueError("Fusion could not recreate the parameter with the new unit.")

    try:
        created.isFavorite = param_favorite
    except Exception:
        pass

    new_token = _parameter_entity_token(created)
    timestamp = _now_metadata_timestamp_ms()
    new_payload = _next_metadata_payload(
        _normalized_metadata_payload(
            group_name=old_group,
            metadata_changed_at=old_record.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=old_record.get(METADATA_REVISION_RECORD_KEY),
            writer_id=old_record.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=old_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
        ),
        old_group,
        timestamp,
    )
    _write_parameter_group_name(created, old_group, timestamp, new_payload)

    stored_records.pop(old_token, None)
    stored_records[new_token] = {
        "order": old_order,
        "name": param_name,
        "current_expression": new_expression,
        "previous_expression": "",
        "current_value": "",
        "previous_value": "",
        "group": old_group,
        METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(new_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
        METADATA_REVISION_RECORD_KEY: _metadata_revision_value(new_payload.get(METADATA_REVISION_RECORD_KEY)),
        METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(new_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
        METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(new_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
    }
    _write_document_order_state({
        "documentId": order_state.get("documentId", ""),
        "documentName": order_state.get("documentName", ""),
        "parameters": stored_records,
        "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
        UI_STATE_RECORD_KEY: order_state.get(UI_STATE_RECORD_KEY, {}),
    })
    return new_token


def _generate_copy_name(design, source_name):
    """Return a collision-safe copy name: {name}_copy, then {name}_copy_2, etc."""
    base = f"{source_name}_copy"
    candidate = base
    counter = 2
    while design.allParameters.itemByName(candidate):
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _copy_parameter(data):
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

    target_name = str(data.get("targetName") or "").strip()
    if not target_name:
        target_name = _generate_copy_name(design, parameter.name)

    validation = _validate_parameter_name_response(target_name)
    if not validation["ok"]:
        raise ValueError(validation["message"])

    source_group = _parameter_group_name(parameter)
    value_input = adsk.core.ValueInput.createByString(parameter.expression)
    created = design.userParameters.add(target_name, value_input, parameter.unit, parameter.comment or "")
    if not created:
        raise ValueError("Fusion could not create the parameter copy.")

    # Restore group and write order record.
    new_token = _parameter_entity_token(created)
    timestamp = _now_metadata_timestamp_ms()
    new_payload = _next_metadata_payload(
        _normalized_metadata_payload(group_name=source_group),
        source_group,
        timestamp,
    )
    _write_parameter_group_name(created, source_group, timestamp, new_payload)

    order_state = _read_document_order_state()
    stored_records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    max_order = max(
        (r.get("order", 0) for r in stored_records.values() if isinstance(r.get("order"), int)),
        default=0,
    )
    stored_records[new_token] = {
        "order": max_order + 1,
        "name": target_name,
        "current_expression": parameter.expression,
        "previous_expression": "",
        "current_value": "",
        "previous_value": "",
        "group": source_group,
        METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(new_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
        METADATA_REVISION_RECORD_KEY: _metadata_revision_value(new_payload.get(METADATA_REVISION_RECORD_KEY)),
        METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(new_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
        METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(new_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
    }
    _write_document_order_state({
        "documentId": order_state.get("documentId", ""),
        "documentName": order_state.get("documentName", ""),
        "parameters": stored_records,
        "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
        UI_STATE_RECORD_KEY: order_state.get(UI_STATE_RECORD_KEY, {}),
    })


def _delete_parameters_batch(data):
    """Batch delete. Returns a result dict (not a full envelope) with ok, message,
    deletedCount, failedCount, and failedDetails. The handler adds 'state'."""
    design = _require_design()
    keys = data.get("keys") if isinstance(data.get("keys"), list) else []
    names = data.get("names") if isinstance(data.get("names"), list) else []

    if not keys and not names:
        return {
            "ok": False,
            "message": '"keys" or "names" array is required.',
            "deletedCount": 0,
            "failedCount": 0,
            "failedDetails": [],
        }

    seen_tokens = set()
    targets = []
    failed_details = []

    for raw_key in keys:
        token = str(raw_key or "").strip()
        if not token or token in seen_tokens:
            continue
        param = _find_user_parameter_by_token(design, token)
        if param:
            seen_tokens.add(token)
            targets.append({"param": param, "key": token, "name": str(param.name or "")})
        else:
            failed_details.append({"key": token, "name": "", "message": "Parameter not found."})

    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        param = design.userParameters.itemByName(name)
        if param:
            token = _parameter_entity_token(param)
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            targets.append({"param": param, "key": token, "name": name})
        else:
            if not any(d.get("name") == name for d in failed_details):
                failed_details.append({"key": "", "name": name, "message": "Parameter not found."})

    deleted_count = 0
    for target in targets:
        try:
            target["param"].deleteMe()
            deleted_count += 1
        except Exception as exc:
            failed_details.append({
                "key": target["key"],
                "name": target["name"],
                "message": f"Fusion could not delete this parameter: {exc}",
            })

    failed_count = len(failed_details)
    ok = deleted_count > 0
    if not ok:
        first_msg = failed_details[0]["message"] if failed_details else "No parameters specified."
        message = f"No parameters were deleted. {first_msg}"
    elif failed_count > 0:
        message = f"{failed_count} parameter(s) could not be deleted."
    else:
        message = ""

    return {
        "ok": ok,
        "message": message,
        "deletedCount": deleted_count,
        "failedCount": failed_count,
        "failedDetails": failed_details,
    }


def _sort_by_timeline_order():
    """Reset stored parameter order to match Fusion's native creation (timeline) order.
    design.userParameters iterates parameters in creation order."""
    design = _require_design()
    order_state = _read_document_order_state()
    stored_records = _resolve_document_order_records(design, order_state.get("parameters") or {})

    params = design.userParameters
    for fusion_index in range(params.count):
        param = params.item(fusion_index)
        if not param:
            continue
        token = _parameter_entity_token(param)
        record = stored_records.get(token)
        if isinstance(record, dict):
            record["order"] = fusion_index
        else:
            stored_records[token] = {
                "order": fusion_index,
                "name": str(param.name or ""),
                "current_expression": str(param.expression or ""),
                "previous_expression": "",
                "current_value": "",
                "previous_value": "",
                "group": _normalize_group_name(_parameter_group_name(param) or ""),
                METADATA_CHANGED_AT_RECORD_KEY: 0,
                METADATA_REVISION_RECORD_KEY: 0,
                METADATA_WRITER_ID_RECORD_KEY: "",
                METADATA_WRITER_VERSION_RECORD_KEY: "",
            }

    _write_document_order_state({
        "documentId": order_state.get("documentId", ""),
        "documentName": order_state.get("documentName", ""),
        "parameters": stored_records,
        "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
        UI_STATE_RECORD_KEY: order_state.get(UI_STATE_RECORD_KEY, {}),
    })


def _serialize_parameters_to_csv(parameters):
    """Serialize a list of parameter dicts to a CSV string (UTF-8, with header row)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["name", "expression", "unit", "comment", "group"])
    for p in parameters:
        writer.writerow([
            p.get("name", ""),
            p.get("expression", ""),
            p.get("unit", ""),
            p.get("comment", ""),
            p.get("group", ""),
        ])
    return buf.getvalue()


def _parse_parameters_csv(content):
    """Parse CSV content into a list of row dicts.

    Returns (rows, error_message). rows is None on parse failure.
    Required columns: name, expression. Optional: unit, comment, group.
    """
    try:
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
        if "name" not in fieldnames or "expression" not in fieldnames:
            return None, 'CSV must include "name" and "expression" columns.'
        rows = []
        for raw_row in reader:
            # Normalize keys to lowercase stripped form.
            row = {k.strip().lower(): str(v or "").strip() for k, v in raw_row.items() if k}
            rows.append({
                "name": row.get("name", ""),
                "expression": row.get("expression", ""),
                "unit": row.get("unit", ""),
                "comment": row.get("comment", ""),
                "group": row.get("group", ""),
            })
        return rows, ""
    except Exception as exc:
        return None, f"CSV parse error: {exc}"


def _export_parameters(data):
    """Export current user parameters to a CSV file.

    If data['filePath'] is provided, writes directly without opening a dialog.
    Returns dict with keys: cancelled, filePath, exportedCount.
    """
    file_path = str(data.get("filePath") or "").strip()
    if not file_path:
        if not ui:
            raise RuntimeError("UI is not available to open a save dialog.")
        dialog = ui.createFileDialog()
        dialog.isMultiSelectEnabled = False
        dialog.title = "Export Parameters — Better Parameters"
        dialog.filter = "CSV Files (*.csv)"
        dialog.filterIndex = 0
        result = dialog.showSave()
        if result != adsk.core.DialogResults.DialogOK:
            return {"cancelled": True, "filePath": "", "exportedCount": 0}
        file_path = str(dialog.filename or "").strip()
        if not file_path:
            return {"cancelled": True, "filePath": "", "exportedCount": 0}
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

    parameters = _collect_user_parameters()
    content = _serialize_parameters_to_csv(parameters)
    # UTF-8 with BOM for Excel compatibility on Windows.
    Path(file_path).write_text(content, encoding="utf-8-sig")
    return {"cancelled": False, "filePath": file_path, "exportedCount": len(parameters)}


def _import_parameters(data, dry_run=False):
    """Import user parameters from a CSV file.

    If data['filePath'] is provided, reads directly without a dialog.
    Conflict policy: 'skip' (default) leaves existing parameters unchanged;
    'overwrite' updates expression and comment of existing parameters.

    dry_run=True runs the full decision logic (validation, conflict checks) without
    applying any mutations to the design. Counts reflect what *would* happen.

    Returns dict with: ok, message, importedCount, skippedCount, failedCount, failedRows.
    Does NOT return state — the action handler adds it.
    """
    conflict_policy = str(data.get("conflictPolicy") or "skip").strip().lower()
    if conflict_policy not in ("skip", "overwrite"):
        conflict_policy = "skip"

    file_path = str(data.get("filePath") or "").strip()
    if not file_path:
        if not ui:
            raise RuntimeError("UI is not available to open a file dialog.")
        dialog = ui.createFileDialog()
        dialog.isMultiSelectEnabled = False
        dialog.title = "Import Parameters — Better Parameters"
        dialog.filter = "CSV Files (*.csv)"
        dialog.filterIndex = 0
        result = dialog.showOpen()
        if result != adsk.core.DialogResults.DialogOK:
            return {
                "ok": False, "message": "Import cancelled.",
                "filePath": "",
                "importedCount": 0, "skippedCount": 0, "failedCount": 0, "failedRows": [],
            }
        file_path = str(dialog.filename or "").strip()
        if not file_path:
            return {
                "ok": False, "message": "Import cancelled.",
                "filePath": "",
                "importedCount": 0, "skippedCount": 0, "failedCount": 0, "failedRows": [],
            }

    try:
        raw = Path(file_path).read_text(encoding="utf-8-sig")
    except Exception as exc:
        raise ValueError(f"Could not read file: {exc}")

    rows, parse_error = _parse_parameters_csv(raw)
    if rows is None:
        raise ValueError(parse_error)

    design = _require_design()
    imported_count = 0
    skipped_count = 0
    failed_rows = []

    for row_index, row in enumerate(rows):
        row_label = row.get("name") or f"row {row_index + 2}"
        name = row.get("name", "")
        expression = row.get("expression", "")
        unit = row.get("unit", "")
        comment = row.get("comment", "")
        group = _normalize_group_name(row.get("group", ""))

        if not name:
            failed_rows.append({"row": row_index + 2, "name": "", "message": "Name is required."})
            continue
        if not expression:
            failed_rows.append({"row": row_index + 2, "name": name, "message": "Expression is required."})
            continue

        existing = design.userParameters.itemByName(name)

        if existing:
            if conflict_policy == "skip":
                skipped_count += 1
                continue
            # overwrite: update expression and comment.
            if dry_run:
                imported_count += 1
            else:
                try:
                    existing.expression = expression
                    if comment:
                        existing.comment = comment
                    # Update group if specified.
                    if group:
                        _set_parameter_group({"name": name, "group": group})
                    imported_count += 1
                except Exception as exc:
                    failed_rows.append({"row": row_index + 2, "name": name, "message": str(exc)})
        else:
            # Validate before creating.
            name_check = _validate_parameter_name_response(name)
            if not name_check["ok"]:
                failed_rows.append({"row": row_index + 2, "name": name, "message": name_check["message"]})
                continue

            expr_check = _validate_expression_response(expression, name, unit)
            if not expr_check["ok"] and not expr_check.get("isIncomplete"):
                failed_rows.append({"row": row_index + 2, "name": name, "message": expr_check["message"]})
                continue

            if dry_run:
                imported_count += 1
            else:
                try:
                    value_input = adsk.core.ValueInput.createByString(expression)
                    created = design.userParameters.add(name, value_input, unit, comment)
                    if not created:
                        raise ValueError("Fusion rejected the parameter.")
                    if group:
                        _set_parameter_group({"name": name, "group": group})
                    imported_count += 1
                except Exception as exc:
                    failed_rows.append({"row": row_index + 2, "name": name, "message": str(exc)})

    failed_count = len(failed_rows)
    ok = True  # file was read and processed successfully even if some rows failed
    if imported_count == 0 and failed_count > 0:
        message = f"No parameters were imported. {failed_rows[0]['message']}" if len(failed_rows) == 1 else f"No parameters were imported. {failed_count} rows failed."
        ok = False
    elif failed_count > 0:
        message = f"{failed_count} row(s) could not be imported."
    elif skipped_count > 0 and imported_count == 0:
        message = f"{skipped_count} parameter(s) already exist and were skipped (conflictPolicy: skip)."
    else:
        message = ""

    return {
        "ok": ok,
        "message": message,
        "filePath": file_path,
        "importedCount": imported_count,
        "skippedCount": skipped_count,
        "failedCount": failed_count,
        "failedRows": failed_rows,
    }


def _normalized_conflict_policy(data):
    """Normalize conflictPolicy from request data. Returns 'skip', 'overwrite', or 'merge-safe'."""
    value = str(data.get("conflictPolicy") or "skip").strip().lower()
    if value not in ("skip", "overwrite", "merge-safe"):
        value = "skip"
    return value


def _extract_apply_knobs(data):
    """Extract and normalize the apply* boolean knobs from a package import request."""
    return {
        "applyExpressionsUnits": bool(data.get("applyExpressionsUnits", False)),
        "applyComments": bool(data.get("applyComments", True)),
        "applyGroups": bool(data.get("applyGroups", True)),
        "applyFavorites": bool(data.get("applyFavorites", True)),
        "applyOrder": bool(data.get("applyOrder", False)),
    }


def _parse_bpmeta_package(raw_text):
    """Parse a .bpmeta.json package string.

    Returns (package_dict, error_message). package_dict is None on failure.
    """
    try:
        package = json.loads(raw_text)
    except Exception as exc:
        return None, f"JSON parse error: {exc}"
    if not isinstance(package, dict):
        return None, "Invalid package format: expected a JSON object."
    schema_version = package.get("schemaVersion")
    if schema_version is None:
        return None, 'Invalid package: missing "schemaVersion".'
    if not isinstance(schema_version, int) or schema_version < 1:
        return None, f'Invalid package: "schemaVersion" must be a positive integer.'
    if schema_version > BPMETA_SCHEMA_VERSION:
        return None, (
            f"Package schema version {schema_version} is newer than supported "
            f"({BPMETA_SCHEMA_VERSION}). Update BetterParameters and try again."
        )
    if not isinstance(package.get("parameters"), list):
        return None, 'Invalid package: "parameters" must be an array.'
    return package, ""


def _open_package_save_dialog(file_path):
    """Open OS save dialog for .bpmeta.json if file_path is empty.

    Returns resolved file_path string, or '' on cancel/failure.
    Raises RuntimeError if UI is unavailable.
    """
    if file_path:
        if not file_path.lower().endswith(".bpmeta.json"):
            file_path += ".bpmeta.json"
        return file_path
    if not ui:
        raise RuntimeError("UI is not available to open a save dialog.")
    dialog = ui.createFileDialog()
    dialog.isMultiSelectEnabled = False
    dialog.title = "Export Parameters Package — Better Parameters"
    dialog.filter = "BP Meta Package (*.bpmeta.json)"
    dialog.filterIndex = 0
    result = dialog.showSave()
    if result != adsk.core.DialogResults.DialogOK:
        return ""
    resolved = str(dialog.filename or "").strip()
    if resolved and not resolved.lower().endswith(".bpmeta.json"):
        resolved += ".bpmeta.json"
    return resolved


def _open_package_open_dialog(file_path):
    """Open OS file-open dialog for .bpmeta.json if file_path is empty.

    Returns resolved file_path string, or '' on cancel/failure.
    Raises RuntimeError if UI is unavailable.
    """
    if file_path:
        return file_path
    if not ui:
        raise RuntimeError("UI is not available to open a file dialog.")
    dialog = ui.createFileDialog()
    dialog.isMultiSelectEnabled = False
    dialog.title = "Import Parameters Package — Better Parameters"
    dialog.filter = "BP Meta Package (*.bpmeta.json)"
    dialog.filterIndex = 0
    result = dialog.showOpen()
    if result != adsk.core.DialogResults.DialogOK:
        return ""
    return str(dialog.filename or "").strip()


def _apply_package_display_order(design, order_updates, previous_state=None):
    """Apply displayOrder indices from a bpmeta package to the current document order state.

    order_updates: list of (displayOrder_int, name_str) tuples.
    Parameters in order_updates are placed first (sorted by displayOrder),
    followed by all other design parameters in their existing relative order.
    """
    if not order_updates:
        return
    if previous_state is None:
        previous_state = _read_document_order_state()

    params = design.userParameters
    name_to_key = {}
    all_keys_in_order = []
    for i in range(params.count):
        param = params.item(i)
        if not param:
            continue
        key = _parameter_entity_token(param)
        name_to_key[param.name] = key
        all_keys_in_order.append(key)

    sorted_updates = sorted(order_updates, key=lambda x: x[0])
    ordered_keys = []
    seen_keys = set()
    for _, name in sorted_updates:
        key = name_to_key.get(name)
        if key and key not in seen_keys:
            ordered_keys.append(key)
            seen_keys.add(key)

    remaining_keys = [k for k in all_keys_in_order if k not in seen_keys]
    final_key_order = ordered_keys + remaining_keys

    key_to_name = {v: k for k, v in name_to_key.items()}
    merged = [{"key": k, "name": key_to_name.get(k, "")} for k in final_key_order]

    _persist_document_order_snapshot(merged, previous_state)
    next_state = _read_document_order_state()
    next_state[UI_STATE_RECORD_KEY] = _bump_ui_state_record(next_state.get(UI_STATE_RECORD_KEY))
    _write_document_order_state(next_state)
    _write_fusion_ui_snapshot(design, _local_ui_snapshot(next_state))


def _export_parameters_package(data):
    """Export user parameters with BP metadata to a .bpmeta.json file.

    Returns dict with: cancelled, filePath, exportedCount.
    """
    include_comments = bool(data.get("includeComments", True))
    include_groups = bool(data.get("includeGroups", True))
    include_favorites = bool(data.get("includeFavorites", True))
    include_order = bool(data.get("includeOrder", False))

    file_path = _open_package_save_dialog(str(data.get("filePath") or "").strip())
    if not file_path:
        return {"cancelled": True, "filePath": "", "exportedCount": 0}

    parameters = _collect_user_parameters()

    design = _design()
    doc_name = ""
    if design:
        try:
            doc_name = str(design.parentDocument.name or "")
        except Exception:
            pass

    records = []
    for idx, p in enumerate(parameters):
        record = {
            "name": p.get("name", ""),
            "expression": p.get("expression", ""),
            "unit": p.get("unit", ""),
        }
        if include_comments:
            record["comment"] = p.get("comment", "")
        if include_groups:
            record["group"] = p.get("group", "")
        if include_favorites:
            record["isFavorite"] = bool(p.get("isFavorite", False))
        if include_order:
            record["displayOrder"] = idx
        # Advisory metadata — always included for round-trip traceability.
        record["metadataRevision"] = int(p.get("metadataRevision") or 0)
        record["metadataChangedAt"] = int(p.get("metadataChangedAt") or 0)
        records.append(record)

    package = {
        "schemaVersion": BPMETA_SCHEMA_VERSION,
        "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sourceDocument": {"name": doc_name},
        "parameters": records,
    }

    Path(file_path).write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"cancelled": False, "filePath": file_path, "exportedCount": len(records)}


def _validate_parameters_package_import(data):
    """Preflight check for importing a .bpmeta.json package. No mutations applied.

    Opens OS dialog if data['filePath'] is absent.
    Returns dict with: cancelled, ok, message, filePath, preview.
    preview contains: addCount, updateCount, skipCount, potentialFailCount, warnings[], failedRows[].
    """
    # Require design before opening dialog so we fail fast on no-document condition.
    design = _require_design()

    conflict_policy = _normalized_conflict_policy(data)
    apply_knobs = _extract_apply_knobs(data)

    file_path = _open_package_open_dialog(str(data.get("filePath") or "").strip())
    if not file_path:
        return {"cancelled": True, "ok": False, "message": "Import cancelled.", "filePath": "", "preview": None}

    try:
        raw = Path(file_path).read_text(encoding="utf-8")
    except Exception as exc:
        raise ValueError(f"Could not read file: {exc}")

    package, parse_error = _parse_bpmeta_package(raw)
    if package is None:
        raise ValueError(parse_error)

    records = package.get("parameters", [])
    seen_names = set()
    failed_rows = []
    add_count = 0
    update_count = 0
    skip_count = 0
    potential_fail_count = 0
    warnings = []

    for idx, record in enumerate(records):
        name = str(record.get("name") or "").strip()

        if not name:
            failed_rows.append({"row": idx + 1, "name": "", "message": "Name is required."})
            continue

        name_folded = name.casefold()
        if name_folded in seen_names:
            failed_rows.append({"row": idx + 1, "name": name, "message": f'Duplicate name "{name}" in package.'})
            continue
        seen_names.add(name_folded)

        existing = design.userParameters.itemByName(name)
        if existing:
            if conflict_policy == "skip":
                skip_count += 1
            else:
                update_count += 1
                if apply_knobs["applyExpressionsUnits"]:
                    expression = str(record.get("expression") or "").strip()
                    if expression:
                        unit = str(record.get("unit") or existing.unit or "").strip()
                        expr_check = _validate_expression_response(expression, name, unit)
                        if not expr_check["ok"] and not expr_check.get("isIncomplete"):
                            potential_fail_count += 1
                            warnings.append(f'"{name}": expression may fail — {expr_check["message"]}')
                    else:
                        potential_fail_count += 1
                        warnings.append(f'"{name}": applyExpressionsUnits is set but expression is missing in package.')
        else:
            expression = str(record.get("expression") or "").strip()
            if not expression:
                failed_rows.append({"row": idx + 1, "name": name, "message": "Expression is required to create a new parameter."})
                continue
            name_check = _validate_parameter_name_response(name)
            if not name_check["ok"]:
                failed_rows.append({"row": idx + 1, "name": name, "message": name_check["message"]})
                continue
            unit = str(record.get("unit") or "").strip()
            expr_check = _validate_expression_response(expression, name, unit)
            if not expr_check["ok"] and not expr_check.get("isIncomplete"):
                potential_fail_count += 1
                warnings.append(f'"{name}": expression may fail — {expr_check["message"]}')
            add_count += 1

    return {
        "cancelled": False,
        "ok": True,
        "message": "",
        "filePath": file_path,
        "preview": {
            "addCount": add_count,
            "updateCount": update_count,
            "skipCount": skip_count,
            "potentialFailCount": potential_fail_count,
            "warnings": warnings,
            "failedRows": failed_rows,
        },
    }


def _import_parameters_package(data, dry_run=False):
    """Import user parameters from a .bpmeta.json package.

    Opens OS dialog if data['filePath'] is absent.
    dry_run=True runs full decision/validation logic without applying mutations.

    Returns dict with: cancelled, ok, message, importedCount, updatedCount, skippedCount, failedCount, failedRows.
    Does NOT return state — the action handler adds it.
    """
    design = _require_design()

    conflict_policy = _normalized_conflict_policy(data)
    apply_knobs = _extract_apply_knobs(data)

    file_path = _open_package_open_dialog(str(data.get("filePath") or "").strip())
    if not file_path:
        return {
            "cancelled": True,
            "ok": False, "message": "Import cancelled.",
            "importedCount": 0, "updatedCount": 0, "skippedCount": 0,
            "failedCount": 0, "failedRows": [],
        }

    try:
        raw = Path(file_path).read_text(encoding="utf-8")
    except Exception as exc:
        raise ValueError(f"Could not read file: {exc}")

    package, parse_error = _parse_bpmeta_package(raw)
    if package is None:
        raise ValueError(parse_error)

    records = package.get("parameters", [])
    previous_state = _read_document_order_state()

    seen_names = set()
    failed_rows = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    order_updates = []  # (displayOrder, name) pairs, collected if applyOrder is enabled

    for idx, record in enumerate(records):
        name = str(record.get("name") or "").strip()

        if not name:
            failed_rows.append({"row": idx + 1, "name": "", "message": "Name is required."})
            continue

        name_folded = name.casefold()
        if name_folded in seen_names:
            failed_rows.append({"row": idx + 1, "name": name, "message": f'Duplicate name "{name}" in package.'})
            continue
        seen_names.add(name_folded)

        expression = str(record.get("expression") or "").strip()
        unit = str(record.get("unit") or "").strip()
        comment = str(record.get("comment") or "")
        group = _normalize_group_name(str(record.get("group") or ""))
        is_favorite = bool(record.get("isFavorite", False))
        display_order = record.get("displayOrder")

        existing = design.userParameters.itemByName(name)
        if existing:
            if conflict_policy == "skip":
                skipped_count += 1
                continue
            # overwrite or merge-safe: apply each checked field independently.
            if dry_run:
                updated_count += 1
                if apply_knobs["applyOrder"] and display_order is not None:
                    order_updates.append((int(display_order), name))
            else:
                try:
                    if apply_knobs["applyExpressionsUnits"] and expression:
                        existing.expression = expression
                    if apply_knobs["applyComments"]:
                        existing.comment = comment
                    if apply_knobs["applyFavorites"]:
                        try:
                            existing.isFavorite = is_favorite
                        except Exception:
                            pass
                    if apply_knobs["applyGroups"] and group:
                        _set_parameter_group({"name": name, "group": group})
                    updated_count += 1
                    if apply_knobs["applyOrder"] and display_order is not None:
                        order_updates.append((int(display_order), name))
                except Exception as exc:
                    failed_rows.append({"row": idx + 1, "name": name, "message": str(exc)})
        else:
            # New parameter: expression is always required.
            if not expression:
                failed_rows.append({"row": idx + 1, "name": name, "message": "Expression is required to create a new parameter."})
                continue
            name_check = _validate_parameter_name_response(name)
            if not name_check["ok"]:
                failed_rows.append({"row": idx + 1, "name": name, "message": name_check["message"]})
                continue
            if dry_run:
                imported_count += 1
                if apply_knobs["applyOrder"] and display_order is not None:
                    order_updates.append((int(display_order), name))
            else:
                try:
                    value_input = adsk.core.ValueInput.createByString(expression)
                    created = design.userParameters.add(
                        name,
                        value_input,
                        unit,
                        comment if apply_knobs["applyComments"] else "",
                    )
                    if not created:
                        raise ValueError("Fusion rejected the parameter.")
                    if apply_knobs["applyFavorites"]:
                        try:
                            created.isFavorite = is_favorite
                        except Exception:
                            pass
                    if apply_knobs["applyGroups"] and group:
                        _set_parameter_group({"name": name, "group": group})
                    imported_count += 1
                    if apply_knobs["applyOrder"] and display_order is not None:
                        order_updates.append((int(display_order), name))
                except Exception as exc:
                    failed_rows.append({"row": idx + 1, "name": name, "message": str(exc)})

    if not dry_run and apply_knobs["applyOrder"] and order_updates:
        try:
            _apply_package_display_order(design, order_updates, previous_state)
        except Exception:
            pass  # Order application failure is non-fatal.

    failed_count = len(failed_rows)
    total_touched = imported_count + updated_count
    if total_touched == 0 and failed_count > 0:
        ok = False
        message = (
            failed_rows[0]["message"]
            if len(failed_rows) == 1
            else f"No parameters were imported. {failed_count} rows failed."
        )
    elif total_touched == 0 and skipped_count > 0:
        ok = True
        message = f"{skipped_count} parameter(s) already exist and were skipped (conflictPolicy: skip)."
    elif failed_count > 0:
        ok = True
        message = f"{failed_count} row(s) could not be imported."
    else:
        ok = True
        message = ""

    return {
        "cancelled": False,
        "ok": ok,
        "message": message,
        "filePath": file_path,
        "importedCount": imported_count,
        "updatedCount": updated_count,
        "skippedCount": skipped_count,
        "failedCount": failed_count,
        "failedRows": failed_rows,
    }


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------

def _get_parameter_dependency_graph():
    """Return dependency graph of user parameters derived from expression token references.

    Nodes: list of {name, expression} for each user parameter.
    Edges: list of {from: name, to: referencedName} pairs, only where the referenced
           name is a known parameter (user or model).

    Returns dict with: nodes, edges.
    """
    design = _require_design()
    user_params = design.userParameters
    known_names = set(_collect_all_parameter_names())

    nodes = []
    edges = []

    for i in range(user_params.count):
        param = user_params.item(i)
        if not param:
            continue
        name = param.name
        expression = param.expression or ""
        nodes.append({"name": name, "expression": expression})
        for match in EXPRESSION_TOKEN_PATTERN.finditer(expression):
            token = match.group(0)
            if token != name and token in known_names:
                edges.append({"from": name, "to": token})

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Backend contract info
# ---------------------------------------------------------------------------

def _get_backend_contract_info():
    """Return stable metadata describing this backend's API surface.

    Useful for FE feature detection and version compatibility checks.
    Returns dict with: contractVersion, bpmetaSchemaVersion, metadataSchemaVersion, actions.
    """
    return {
        "contractVersion": CONTRACT_VERSION,
        "bpmetaSchemaVersion": BPMETA_SCHEMA_VERSION,
        "metadataSchemaVersion": METADATA_SCHEMA_VERSION,
        "actions": {
            "readOnly": list(_READ_ONLY_ACTIONS),
            "mutating": list(_MUTATING_ACTIONS),
        },
    }


# ---------------------------------------------------------------------------
# Test-support: seed and reset
# ---------------------------------------------------------------------------

_BPTEST_PREFIX = "_bptest_"


def _seed_test_parameters(data):
    """Create or update test parameters in the current design.

    data['parameters'] must be a list of {name, expression, unit, comment?, group?, isFavorite?}.
    Parameters are prefixed with _BPTEST_PREFIX to avoid collisions unless name already starts
    with the prefix.

    Returns dict with: ok, message, seededCount, failedRows.
    """
    design = _require_design()
    seed_records = data.get("parameters") or []
    if not isinstance(seed_records, list):
        raise BPValidationError('"parameters" must be an array.')

    seeded_count = 0
    failed_rows = []

    for idx, record in enumerate(seed_records):
        raw_name = str(record.get("name") or "").strip()
        if not raw_name:
            failed_rows.append({"row": idx + 1, "name": "", "message": "Name is required."})
            continue
        name = raw_name if raw_name.startswith(_BPTEST_PREFIX) else (_BPTEST_PREFIX + raw_name)
        expression = str(record.get("expression") or "").strip()
        unit = str(record.get("unit") or "").strip()
        comment = str(record.get("comment") or "")
        group = _normalize_group_name(str(record.get("group") or ""))
        is_favorite = bool(record.get("isFavorite", False))

        if not expression:
            failed_rows.append({"row": idx + 1, "name": name, "message": "Expression is required."})
            continue

        try:
            existing = design.userParameters.itemByName(name)
            if existing:
                existing.expression = expression
                existing.comment = comment
                try:
                    existing.isFavorite = is_favorite
                except Exception:
                    pass
            else:
                value_input = adsk.core.ValueInput.createByString(expression)
                created = design.userParameters.add(name, value_input, unit, comment)
                if not created:
                    raise ValueError("Fusion rejected the parameter.")
                try:
                    created.isFavorite = is_favorite
                except Exception:
                    pass
            if group:
                _set_parameter_group({"name": name, "group": group})
            seeded_count += 1
        except Exception as exc:
            failed_rows.append({"row": idx + 1, "name": name, "message": str(exc)})

    failed_count = len(failed_rows)
    ok = seeded_count > 0 or failed_count == 0
    message = f"{failed_count} seed record(s) failed." if failed_count else ""
    return {"ok": ok, "message": message, "seededCount": seeded_count, "failedRows": failed_rows}


def _reset_test_state(data):
    """Delete all _bptest_* parameters from the current design and clear their metadata.

    Requires data['confirm'] == "RESET" as a safety guard.

    Returns dict with: ok, message, clearedCount.
    """
    if str(data.get("confirm") or "") != "RESET":
        raise BPValidationError('Must set confirm="RESET" to perform reset.')

    design = _require_design()
    params = design.userParameters
    to_delete = []
    for i in range(params.count):
        param = params.item(i)
        if param and param.name and param.name.startswith(_BPTEST_PREFIX):
            to_delete.append(param.name)

    cleared_count = 0
    for name in to_delete:
        try:
            param = design.userParameters.itemByName(name)
            if param:
                param.deleteMe()
                cleared_count += 1
        except Exception:
            pass

    return {"ok": True, "message": "", "clearedCount": cleared_count}


# ---------------------------------------------------------------------------
# Self-test framework
# ---------------------------------------------------------------------------

class _BPTestContext:
    """Lightweight test result accumulator used by _bptest_* functions."""

    def __init__(self, name):
        self.name = name
        self.passed = True
        self.failures = []

    def assert_equal(self, actual, expected, label=""):
        if actual != expected:
            msg = f"{label}: expected {expected!r}, got {actual!r}" if label else f"expected {expected!r}, got {actual!r}"
            self.failures.append(msg)
            self.passed = False

    def assert_true(self, condition, label=""):
        if not condition:
            msg = label or "expected True, got False"
            self.failures.append(msg)
            self.passed = False

    def assert_false(self, condition, label=""):
        if condition:
            msg = label or "expected False, got True"
            self.failures.append(msg)
            self.passed = False

    def assert_in(self, item, container, label=""):
        if item not in container:
            msg = f"{label}: {item!r} not in {container!r}" if label else f"{item!r} not in collection"
            self.failures.append(msg)
            self.passed = False

    def result(self):
        return {
            "name": self.name,
            "passed": self.passed,
            "failures": self.failures,
        }


def _bptest_smoke_contract_info(ctx):
    """Smoke: getBackendContractInfo returns expected keys."""
    info = _get_backend_contract_info()
    ctx.assert_in("contractVersion", info, "contractVersion present")
    ctx.assert_in("bpmetaSchemaVersion", info, "bpmetaSchemaVersion present")
    ctx.assert_in("actions", info, "actions present")
    ctx.assert_in("readOnly", info["actions"], "actions.readOnly present")
    ctx.assert_in("mutating", info["actions"], "actions.mutating present")
    ctx.assert_true(isinstance(info["actions"]["readOnly"], list), "readOnly is list")
    ctx.assert_true(isinstance(info["actions"]["mutating"], list), "mutating is list")


def _bptest_smoke_dependency_graph(ctx):
    """Smoke: getParameterDependencyGraph returns nodes/edges when design is open."""
    graph = _get_parameter_dependency_graph()
    ctx.assert_in("nodes", graph, "nodes key present")
    ctx.assert_in("edges", graph, "edges key present")
    ctx.assert_true(isinstance(graph["nodes"], list), "nodes is list")
    ctx.assert_true(isinstance(graph["edges"], list), "edges is list")


def _bptest_smoke_dry_run_import_csv(ctx):
    """Smoke: dry_run=True on importParameters does not mutate design."""
    design = _design()
    if not design:
        ctx.assert_true(False, "No design open — skip")
        return
    before_count = design.userParameters.count
    # Build a minimal in-memory CSV for a param that should not exist.
    test_name = _BPTEST_PREFIX + "dryrun_csv_smoke"
    existing = design.userParameters.itemByName(test_name)
    if existing:
        # If somehow present, skip to avoid false positive.
        return
    import io
    csv_content = f"name,expression,unit,comment,group\n{test_name},5 mm,mm,,\n"
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
    try:
        tmp.write(csv_content)
        tmp.close()
        result = _import_parameters({"filePath": tmp.name, "conflictPolicy": "overwrite"}, dry_run=True)
        ctx.assert_true(result["ok"], "dry_run import ok")
        ctx.assert_equal(result["importedCount"], 1, "importedCount=1")
        after_count = design.userParameters.count
        ctx.assert_equal(after_count, before_count, "parameter count unchanged after dry_run")
        still_absent = design.userParameters.itemByName(test_name)
        ctx.assert_true(still_absent is None, "test param not created by dry_run")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _bptest_smoke_validate_name(ctx):
    """Smoke: _validate_parameter_name_response accepts valid names and rejects empty."""
    ok_result = _validate_parameter_name_response("width")
    ctx.assert_true(ok_result["ok"], "valid name accepted")
    bad_result = _validate_parameter_name_response("")
    ctx.assert_false(bad_result["ok"], "empty name rejected")
    digit_result = _validate_parameter_name_response("1bad")
    ctx.assert_false(digit_result["ok"], "digit-start name rejected")


def _bptest_smoke_bpmeta_parse(ctx):
    """Smoke: _parse_bpmeta_package accepts valid and rejects bad input."""
    valid_json = json.dumps({
        "schemaVersion": 1,
        "exportedAt": "2026-01-01T00:00:00Z",
        "sourceDocument": {"name": "Test"},
        "parameters": [],
    })
    pkg, err = _parse_bpmeta_package(valid_json)
    ctx.assert_true(pkg is not None, "valid package parsed")
    ctx.assert_equal(err, "", "no error for valid package")
    bad_pkg, bad_err = _parse_bpmeta_package("not json")
    ctx.assert_true(bad_pkg is None, "invalid JSON → None")
    ctx.assert_true(len(bad_err) > 0, "error message non-empty")


_BP_TEST_REGISTRY = [
    ("smoke/contract_info", _bptest_smoke_contract_info),
    ("smoke/dependency_graph", _bptest_smoke_dependency_graph),
    ("smoke/dry_run_import_csv", _bptest_smoke_dry_run_import_csv),
    ("smoke/validate_name", _bptest_smoke_validate_name),
    ("smoke/bpmeta_parse", _bptest_smoke_bpmeta_parse),
]


def _run_self_test_suite(data):
    """Run all registered in-process self-tests.

    data['filter'] (optional): only run tests whose name contains this substring.

    Returns dict with: totalCount, passedCount, failedCount, results[].
    """
    filter_str = str(data.get("filter") or "").strip().lower()
    results = []
    for test_name, test_fn in _BP_TEST_REGISTRY:
        if filter_str and filter_str not in test_name.lower():
            continue
        ctx = _BPTestContext(test_name)
        try:
            test_fn(ctx)
        except Exception as exc:
            ctx.passed = False
            ctx.failures.append(f"Exception: {exc}")
        results.append(ctx.result())

    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count
    return {
        "totalCount": len(results),
        "passedCount": passed_count,
        "failedCount": failed_count,
        "results": results,
    }


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
        return {"ok": False, "message": "Expression is required.", "isIncomplete": False}

    parameter_names = set(_collect_all_parameter_names())
    allowed_identifiers = set(ALLOWED_EXPRESSION_IDENTIFIERS)
    allowed_identifiers.update(_known_unit_identifiers())

    unknown_tokens = []
    for match in EXPRESSION_TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if current_parameter_name and token == current_parameter_name:
            return {
                "ok": False,
                "message": f'Expression cannot reference "{current_parameter_name}" exactly because that is the parameter currently being edited.',
                "isIncomplete": False,
            }
        if token in parameter_names or token in allowed_identifiers:
            continue
        unknown_tokens.append(token)

    design = _design()
    if design:
        try:
            validate_units = units or design.unitsManager.defaultLengthUnits or "mm"
            if design.unitsManager.isValidExpression(text, validate_units):
                return {"ok": True, "message": "", "isIncomplete": False}
            if unknown_tokens:
                token = unknown_tokens[0]
                case_hint = _case_sensitive_parameter_hint(token, parameter_names)
                if case_hint:
                    return {
                        "ok": False,
                        "message": f'Unknown parameter name "{token}". Parameter names are case sensitive. Did you mean "{case_hint}"?',
                        "isIncomplete": False,
                    }
                return {
                    "ok": False,
                    "message": f'Unknown parameter name "{token}". Parameter names are case sensitive and must match an existing parameter exactly.',
                    "isIncomplete": False,
                }
            if not design.unitsManager.isValidExpression(text, validate_units):
                incomplete_hint = _incomplete_expression_hint(text)
                if incomplete_hint:
                    return {
                        "ok": False,
                        "message": incomplete_hint,
                        "isIncomplete": True,
                    }
                mismatch_hint = _dimension_mismatch_hint(text, validate_units, design.unitsManager)
                if mismatch_hint:
                    return {
                        "ok": False,
                        "message": mismatch_hint,
                        "isIncomplete": False,
                    }
                return {
                    "ok": False,
                    "message": "Expression syntax is invalid. Use explicit operators between terms; parentheses do not imply multiplication.",
                    "isIncomplete": False,
                }
        except Exception:
            pass

    if unknown_tokens:
        token = unknown_tokens[0]
        case_hint = _case_sensitive_parameter_hint(token, parameter_names)
        if case_hint:
            return {
                "ok": False,
                "message": f'Unknown parameter name "{token}". Parameter names are case sensitive. Did you mean "{case_hint}"?',
                "isIncomplete": False,
            }
        return {
            "ok": False,
            "message": f'Unknown parameter name "{token}". Parameter names are case sensitive and must match an existing parameter exactly.',
            "isIncomplete": False,
        }

    return {"ok": True, "message": "", "isIncomplete": False}


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


def _dimension_mismatch_hint(expression_text, target_unit, units_manager):
    if units_manager is None:
        return ""

    target = str(target_unit or "").strip()
    if not target:
        return ""
    if target.lower() == "text":
        return ""

    target_valid = True
    try:
        # If target unit itself is not a valid Fusion unit token, do not emit mismatch hint.
        target_valid = bool(
            units_manager.isValidExpression("1", target)
            or units_manager.isValidExpression(f"1 {target}", target)
        )
    except Exception:
        target_valid = False
    if not target_valid:
        return ""

    text = str(expression_text or "").strip()
    if not text:
        return ""

    try:
        for probe_unit in DIMENSION_PROBE_UNITS:
            if not probe_unit:
                continue
            if probe_unit.lower() == target.lower():
                continue
            try:
                if units_manager.isValidExpression(text, probe_unit):
                    return (
                        f'Expression units are incompatible with "{target}". '
                        "Check dimensionality (for example area vs length)."
                    )
            except Exception:
                continue
    except Exception:
        return ""

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


def _open_help_url(data):
    url = str(data.get("url") if isinstance(data, dict) else "").strip()
    if not url:
        return {"ok": False, "message": '"url" is required.'}
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"ok": False, "message": '"url" must start with "http://" or "https://".'}
    try:
        webbrowser.open(url)
        return {"ok": True, "message": ""}
    except Exception as exc:
        return {"ok": False, "message": f"Could not open URL: {exc}"}


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def _clipboard_write_win32(text):
    """Write text to the Windows clipboard using Win32 API via ctypes.

    Bypasses WebView clipboard security restrictions entirely.
    Uses CF_UNICODETEXT (UTF-16-LE) for full Unicode support.
    Raises RuntimeError on any Win32 failure.
    """
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    encoded = (text + "\x00").encode("utf-16-le")
    size = len(encoded)

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not h_mem:
        raise RuntimeError("GlobalAlloc failed.")

    h_mem_owned_by_clipboard = False
    try:
        p = kernel32.GlobalLock(h_mem)
        if not p:
            raise RuntimeError("GlobalLock failed.")
        ctypes.memmove(p, encoded, size)
        kernel32.GlobalUnlock(h_mem)

        if not user32.OpenClipboard(None):
            raise RuntimeError("OpenClipboard failed.")
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                raise RuntimeError("SetClipboardData failed.")
            # Clipboard now owns the memory — do not free.
            h_mem_owned_by_clipboard = True
        finally:
            user32.CloseClipboard()
    finally:
        if not h_mem_owned_by_clipboard:
            kernel32.GlobalFree(h_mem)


def _clipboard_write_macos(text):
    """Write text to the macOS clipboard via pbcopy subprocess.

    pbcopy reads stdin and places it on the general pasteboard.
    Raises subprocess.CalledProcessError on failure.
    """
    subprocess.run(
        ["pbcopy"],
        input=text.encode("utf-8"),
        check=True,
        capture_output=True,
        timeout=3,
    )


def _copy_to_clipboard(data):
    """Write text to the OS clipboard.

    Uses Win32 ctypes API on Windows, pbcopy subprocess on macOS.
    Bypasses WebView clipboard security restrictions entirely — reliable
    across all Fusion 360 WebView/QtWebEngine variants.

    Raises BPValidationError if "text" is missing.
    Raises BPError (ERROR_IO) if the OS clipboard write fails.
    Does not require an active design.
    """
    text = str(data.get("text") or "")
    if not text:
        raise BPValidationError('"text" is required and must be non-empty.')

    current_platform = platform.system()
    try:
        if current_platform == "Windows":
            _clipboard_write_win32(text)
        elif current_platform == "Darwin":
            _clipboard_write_macos(text)
        else:
            raise BPError(
                f"Clipboard write not supported on platform: {current_platform!r}. "
                "Use the FE fallback (navigator.clipboard / execCommand).",
                ERROR_IO,
            )
    except BPError:
        raise
    except Exception as exc:
        raise BPError(f"Clipboard write failed: {exc}", ERROR_IO) from exc

    return {"ok": True, "message": ""}


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
        raise BPNoDesignError()
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


def _metadata_revision_value(value):
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


def _metadata_writer_id_value(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 120:
        text = text[:120]
    return text


def _metadata_writer_version_value(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 64:
        text = text[:64]
    return text


def _writer_id_path():
    return _app_support_root() / "writer_id.txt"


def _current_writer_id():
    path = _writer_id_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    if path.exists():
        try:
            existing = _metadata_writer_id_value(path.read_text(encoding="utf-8"))
            if existing:
                return existing
        except Exception:
            pass

    created = str(uuid.uuid4())
    try:
        path.write_text(created, encoding="utf-8")
    except Exception:
        pass
    return created


def _current_writer_version():
    return _metadata_writer_version_value(_current_addin_version())


def _normalized_metadata_payload(group_name="", metadata_changed_at=0, revision=0, writer_id="", writer_version=""):
    changed_at = _metadata_changed_at_value(metadata_changed_at)
    resolved_writer_id = _metadata_writer_id_value(writer_id) or _current_writer_id()
    resolved_writer_version = _metadata_writer_version_value(writer_version) or _current_writer_version()
    resolved_revision = _metadata_revision_value(revision)
    if changed_at <= 0:
        changed_at = _now_metadata_timestamp_ms()
    if resolved_revision <= 0:
        resolved_revision = 1
    return {
        "group": _normalize_group_name(group_name or ""),
        METADATA_CHANGED_AT_RECORD_KEY: changed_at,
        METADATA_REVISION_RECORD_KEY: resolved_revision,
        METADATA_WRITER_ID_RECORD_KEY: resolved_writer_id,
        METADATA_WRITER_VERSION_RECORD_KEY: resolved_writer_version,
    }


def _is_metadata_newer(left_payload, right_payload):
    left = left_payload or {}
    right = right_payload or {}
    left_revision = _metadata_revision_value(left.get(METADATA_REVISION_RECORD_KEY))
    right_revision = _metadata_revision_value(right.get(METADATA_REVISION_RECORD_KEY))
    if left_revision != right_revision:
        return left_revision > right_revision

    left_changed_at = _metadata_changed_at_value(left.get(METADATA_CHANGED_AT_RECORD_KEY))
    right_changed_at = _metadata_changed_at_value(right.get(METADATA_CHANGED_AT_RECORD_KEY))
    if left_changed_at != right_changed_at:
        return left_changed_at > right_changed_at

    left_writer_id = _metadata_writer_id_value(left.get(METADATA_WRITER_ID_RECORD_KEY))
    right_writer_id = _metadata_writer_id_value(right.get(METADATA_WRITER_ID_RECORD_KEY))
    if left_writer_id != right_writer_id:
        return left_writer_id > right_writer_id

    left_group = _normalize_group_name(left.get("group") or "")
    right_group = _normalize_group_name(right.get("group") or "")
    if left_group != right_group:
        return bool(left_group)
    return False


def _choose_latest_metadata(left_payload, right_payload):
    left = _normalized_metadata_payload(
        group_name=(left_payload or {}).get("group") or "",
        metadata_changed_at=(left_payload or {}).get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=(left_payload or {}).get(METADATA_REVISION_RECORD_KEY),
        writer_id=(left_payload or {}).get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=(left_payload or {}).get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    right = _normalized_metadata_payload(
        group_name=(right_payload or {}).get("group") or "",
        metadata_changed_at=(right_payload or {}).get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=(right_payload or {}).get(METADATA_REVISION_RECORD_KEY),
        writer_id=(right_payload or {}).get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=(right_payload or {}).get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    if _is_metadata_newer(left, right):
        return left
    return right


def _next_metadata_payload(previous_payload, group_name, metadata_changed_at=None):
    previous = previous_payload or {}
    previous_revision = _metadata_revision_value(previous.get(METADATA_REVISION_RECORD_KEY))
    changed_at = _metadata_changed_at_value(metadata_changed_at)
    if changed_at <= 0:
        changed_at = _now_metadata_timestamp_ms()
    return _normalized_metadata_payload(
        group_name=group_name,
        metadata_changed_at=changed_at,
        revision=previous_revision + 1 if previous_revision > 0 else 1,
        writer_id=_current_writer_id(),
        writer_version=_current_writer_version(),
    )


def _metadata_payload_content_hash(payload_by_key):
    normalized = {}
    for key, value in (payload_by_key or {}).items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(value, dict):
            continue
        normalized[key] = {
            "group": _normalize_group_name(value.get("group") or ""),
            "changedAt": _metadata_changed_at_value(value.get(METADATA_CHANGED_AT_RECORD_KEY)),
            "revision": _metadata_revision_value(value.get(METADATA_REVISION_RECORD_KEY)),
            "writerId": _metadata_writer_id_value(value.get(METADATA_WRITER_ID_RECORD_KEY)),
            "writerVersion": _metadata_writer_version_value(value.get(METADATA_WRITER_VERSION_RECORD_KEY)),
        }
    encoded = json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def _read_document_metadata_map(design):
    for owner in _document_metadata_owner_candidates(design):
        attributes = getattr(owner, "attributes", None)
        if attributes is None:
            continue
        try:
            attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_DOCUMENT_METADATA_MAP_NAME)
        except Exception:
            attribute = None
        if attribute is None:
            continue

        try:
            loaded = json.loads(str(attribute.value or ""))
        except Exception:
            continue
        if not isinstance(loaded, dict):
            continue

        normalized = {}
        for key, value in loaded.items():
            if not isinstance(key, str) or not key:
                continue
            if not isinstance(value, dict):
                continue
            normalized[key] = {
                "group": _normalize_group_name(value.get("group") or ""),
                METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(value.get(METADATA_CHANGED_AT_RECORD_KEY)),
                METADATA_REVISION_RECORD_KEY: _metadata_revision_value(value.get(METADATA_REVISION_RECORD_KEY)),
                METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(value.get(METADATA_WRITER_ID_RECORD_KEY)),
                METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(value.get(METADATA_WRITER_VERSION_RECORD_KEY)),
            }
        return normalized
    return {}


def _write_document_metadata_map(design, metadata_map):
    payload = {}
    for key, value in (metadata_map or {}).items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(value, dict):
            continue
        payload[key] = {
            "group": _normalize_group_name(value.get("group") or ""),
            METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(value.get(METADATA_CHANGED_AT_RECORD_KEY)),
            METADATA_REVISION_RECORD_KEY: _metadata_revision_value(value.get(METADATA_REVISION_RECORD_KEY)),
            METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(value.get(METADATA_WRITER_ID_RECORD_KEY)),
            METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(value.get(METADATA_WRITER_VERSION_RECORD_KEY)),
        }

    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    for owner in _document_metadata_owner_candidates(design):
        attributes = getattr(owner, "attributes", None)
        if attributes is None:
            continue
        try:
            attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_DOCUMENT_METADATA_MAP_NAME)
        except Exception:
            attribute = None

        if attribute is not None:
            try:
                attribute.value = serialized
                return True
            except Exception:
                pass

        try:
            attributes.add(ATTRIBUTE_NAMESPACE, ATTRIBUTE_DOCUMENT_METADATA_MAP_NAME, serialized)
            return True
        except Exception:
            pass
    return False


def _read_document_metadata_state(design):
    defaults = {
        "schemaVersion": METADATA_SCHEMA_VERSION,
        "docMetaVersion": 0,
        "lastChangedAt": 0,
        "lastWriterId": "",
        "paramCountHint": 0,
        "contentHash": "",
        "parameterOrder": [],
        "groupUi": {"order": [], "collapsed": {}},
        UI_STATE_RECORD_KEY: {
            UI_STATE_REVISION_KEY: 0,
            UI_STATE_CHANGED_AT_KEY: 0,
            UI_STATE_WRITER_ID_KEY: "",
            UI_STATE_WRITER_VERSION_KEY: "",
        },
    }
    for owner in _document_metadata_owner_candidates(design):
        attributes = getattr(owner, "attributes", None)
        if attributes is None:
            continue
        try:
            attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_DOCUMENT_METADATA_STATE_NAME)
        except Exception:
            attribute = None
        if attribute is None:
            continue
        try:
            payload = json.loads(str(attribute.value or ""))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        return {
            "schemaVersion": int(payload.get("schemaVersion") or METADATA_SCHEMA_VERSION),
            "docMetaVersion": max(0, int(payload.get("docMetaVersion") or 0)),
            "lastChangedAt": _metadata_changed_at_value(payload.get("lastChangedAt")),
            "lastWriterId": _metadata_writer_id_value(payload.get("lastWriterId")),
            "paramCountHint": max(0, int(payload.get("paramCountHint") or 0)),
            "contentHash": str(payload.get("contentHash") or ""),
            "parameterOrder": _normalized_parameter_order(payload.get("parameterOrder")),
            "groupUi": _normalized_group_ui_state(payload.get("groupUi")),
            UI_STATE_RECORD_KEY: _normalized_ui_state_record(payload.get(UI_STATE_RECORD_KEY)),
        }
    return defaults


def _write_document_metadata_state(design, state):
    if not design:
        return False
    payload = {
        "schemaVersion": int((state or {}).get("schemaVersion") or METADATA_SCHEMA_VERSION),
        "docMetaVersion": max(0, int((state or {}).get("docMetaVersion") or 0)),
        "lastChangedAt": _metadata_changed_at_value((state or {}).get("lastChangedAt")),
        "lastWriterId": _metadata_writer_id_value((state or {}).get("lastWriterId")),
        "paramCountHint": max(0, int((state or {}).get("paramCountHint") or 0)),
        "contentHash": str((state or {}).get("contentHash") or ""),
        "parameterOrder": _normalized_parameter_order((state or {}).get("parameterOrder")),
        "groupUi": _normalized_group_ui_state((state or {}).get("groupUi")),
        UI_STATE_RECORD_KEY: _normalized_ui_state_record((state or {}).get(UI_STATE_RECORD_KEY)),
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    for owner in _document_metadata_owner_candidates(design):
        attributes = getattr(owner, "attributes", None)
        if attributes is None:
            continue
        try:
            attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_DOCUMENT_METADATA_STATE_NAME)
        except Exception:
            attribute = None
        if attribute is not None:
            try:
                attribute.value = serialized
                return True
            except Exception:
                pass
        try:
            attributes.add(ATTRIBUTE_NAMESPACE, ATTRIBUTE_DOCUMENT_METADATA_STATE_NAME, serialized)
            return True
        except Exception:
            pass
    return False


def _bump_document_metadata_state(design, metadata_payload_by_key):
    if not design:
        return False
    current = _read_document_metadata_state(design)
    content_hash = _metadata_payload_content_hash(metadata_payload_by_key)
    changed = content_hash != str(current.get("contentHash") or "")
    next_state = {
        "schemaVersion": METADATA_SCHEMA_VERSION,
        "docMetaVersion": (int(current.get("docMetaVersion") or 0) + 1) if changed else int(current.get("docMetaVersion") or 0),
        "lastChangedAt": _now_metadata_timestamp_ms() if changed else _metadata_changed_at_value(current.get("lastChangedAt")),
        "lastWriterId": _current_writer_id() if changed else _metadata_writer_id_value(current.get("lastWriterId")),
        "paramCountHint": len(metadata_payload_by_key or {}),
        "contentHash": content_hash,
    }
    return _write_document_metadata_state(design, next_state)


def _ui_state_is_newer(left_state, right_state):
    left = _normalized_ui_state_record(left_state)
    right = _normalized_ui_state_record(right_state)
    left_revision = _metadata_revision_value(left.get(UI_STATE_REVISION_KEY))
    right_revision = _metadata_revision_value(right.get(UI_STATE_REVISION_KEY))
    if left_revision != right_revision:
        return left_revision > right_revision
    left_changed_at = _metadata_changed_at_value(left.get(UI_STATE_CHANGED_AT_KEY))
    right_changed_at = _metadata_changed_at_value(right.get(UI_STATE_CHANGED_AT_KEY))
    if left_changed_at != right_changed_at:
        return left_changed_at > right_changed_at
    left_writer = _metadata_writer_id_value(left.get(UI_STATE_WRITER_ID_KEY))
    right_writer = _metadata_writer_id_value(right.get(UI_STATE_WRITER_ID_KEY))
    return left_writer > right_writer


def _local_ui_snapshot(order_state):
    normalized = order_state if isinstance(order_state, dict) else {}
    records = normalized.get("parameters") if isinstance(normalized.get("parameters"), dict) else {}
    return {
        UI_STATE_RECORD_KEY: _normalized_ui_state_record(normalized.get(UI_STATE_RECORD_KEY)),
        "groupUi": _normalized_group_ui_state(normalized.get("groupUi")),
        "parameterOrder": _collect_parameter_order_from_records(records),
    }


def _fusion_ui_snapshot(design):
    state = _read_document_metadata_state(design)
    return {
        UI_STATE_RECORD_KEY: _normalized_ui_state_record(state.get(UI_STATE_RECORD_KEY)),
        "groupUi": _normalized_group_ui_state(state.get("groupUi")),
        "parameterOrder": _normalized_parameter_order(state.get("parameterOrder")),
    }


def _write_fusion_ui_snapshot(design, ui_snapshot):
    if not design:
        return False
    current = _read_document_metadata_state(design)
    next_state = dict(current)
    next_state["groupUi"] = _normalized_group_ui_state((ui_snapshot or {}).get("groupUi"))
    next_state["parameterOrder"] = _normalized_parameter_order((ui_snapshot or {}).get("parameterOrder"))
    next_state[UI_STATE_RECORD_KEY] = _normalized_ui_state_record((ui_snapshot or {}).get(UI_STATE_RECORD_KEY))
    return _write_document_metadata_state(design, next_state)


def _sync_ui_state_between_local_and_fusion(design, order_state):
    if not design:
        return order_state if isinstance(order_state, dict) else _read_document_order_state()

    local_state = order_state if isinstance(order_state, dict) else _read_document_order_state()
    local_snapshot = _local_ui_snapshot(local_state)
    fusion_snapshot = _fusion_ui_snapshot(design)
    local_ui_state = local_snapshot.get(UI_STATE_RECORD_KEY)
    fusion_ui_state = fusion_snapshot.get(UI_STATE_RECORD_KEY)

    if _ui_state_is_newer(fusion_ui_state, local_ui_state):
        records = local_state.get("parameters") if isinstance(local_state.get("parameters"), dict) else {}
        if not records:
            params = design.userParameters
            for index in range(params.count):
                parameter = params.item(index)
                if not parameter:
                    continue
                key = _parameter_entity_token(parameter)
                if not key:
                    continue
                records[key] = {
                    "order": index,
                    "name": str(parameter.name or ""),
                    "current_expression": str(parameter.expression or ""),
                    "previous_expression": "",
                    "current_value": "",
                    "previous_value": "",
                    "group": _normalize_group_name(_parameter_group_name(parameter) or ""),
                    METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(_parameter_metadata_changed_at(parameter)),
                    METADATA_REVISION_RECORD_KEY: _metadata_revision_value(_parameter_metadata_payload(parameter).get(METADATA_REVISION_RECORD_KEY)),
                    METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(_parameter_metadata_payload(parameter).get(METADATA_WRITER_ID_RECORD_KEY)),
                    METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(_parameter_metadata_payload(parameter).get(METADATA_WRITER_VERSION_RECORD_KEY)),
                }
        applied_order = _normalized_parameter_order(fusion_snapshot.get("parameterOrder"), records.keys())
        _apply_parameter_order_to_records(records, applied_order)
        local_state = {
            "documentId": local_state.get("documentId", ""),
            "documentName": local_state.get("documentName", ""),
            "parameters": records,
            "groupUi": _normalized_group_ui_state(fusion_snapshot.get("groupUi")),
            UI_STATE_RECORD_KEY: _normalized_ui_state_record(fusion_ui_state),
        }
        _write_document_order_state(local_state)
        return local_state

    if _ui_state_is_newer(local_ui_state, fusion_ui_state):
        _write_fusion_ui_snapshot(design, local_snapshot)
    return local_state


def _document_metadata_owner_candidates(design):
    owners = []
    for candidate in (
        design,
        _safe_call(lambda: design.rootComponent) if design else None,
        _safe_call(lambda: design.userParameters) if design else None,
        _safe_call(lambda: design.allParameters) if design else None,
        app.activeDocument if app else None,
    ):
        if not candidate:
            continue
        if candidate in owners:
            continue
        owners.append(candidate)
    return owners


def _owner_debug_label(owner):
    if not owner:
        return "None"
    type_name = type(owner).__name__
    object_type = ""
    try:
        object_type = str(getattr(owner, "objectType", "") or "")
    except Exception:
        object_type = ""
    if object_type:
        return f"{type_name}<{object_type}>"
    return type_name


def _write_document_attribute_with_diagnostics(owners, namespace, name, value):
    details = {
        "ok": False,
        "ownerTypes": [],
        "errors": [],
    }
    owner_labels = []
    for owner in owners or []:
        owner_label = _owner_debug_label(owner)
        owner_labels.append(owner_label)
        attributes = getattr(owner, "attributes", None)
        if attributes is None:
            details["errors"].append(f"{owner_label}: no attributes collection")
            continue

        attribute = None
        try:
            attribute = attributes.itemByName(namespace, name)
        except Exception as error:
            details["errors"].append(f"{owner_label}: itemByName failed: {error}")

        if attribute is not None:
            try:
                attribute.value = value
                details["ok"] = True
                details["ownerTypes"] = owner_labels
                return details
            except Exception as error:
                details["errors"].append(f"{owner_label}: attribute.value failed: {error}")

        try:
            attributes.add(namespace, name, value)
            details["ok"] = True
            details["ownerTypes"] = owner_labels
            return details
        except Exception as error:
            details["errors"].append(f"{owner_label}: attributes.add failed: {error}")

    details["ownerTypes"] = owner_labels
    return details


def _document_metadata_entry(design, parameter):
    if not design or not parameter:
        return {}
    parameter_key = _parameter_entity_token(parameter)
    if not parameter_key:
        return {}

    metadata_map = _read_document_metadata_map(design)
    map_entry = metadata_map.get(parameter_key) if isinstance(metadata_map.get(parameter_key), dict) else {}
    item_entry = _read_document_metadata_item_entry(design, parameter_key)
    return _choose_latest_metadata(map_entry, item_entry)


def _set_document_metadata_entry(
    design,
    parameter,
    group_name=None,
    metadata_changed_at=None,
    metadata_revision=None,
    metadata_writer_id=None,
    metadata_writer_version=None,
):
    if not design or not parameter:
        return False

    parameter_key = _parameter_entity_token(parameter)
    if not parameter_key:
        return False

    metadata_map = _read_document_metadata_map(design)
    current_entry = metadata_map.get(parameter_key) if isinstance(metadata_map.get(parameter_key), dict) else {}
    next_payload = _normalized_metadata_payload(
        group_name=group_name if group_name is not None else current_entry.get("group") or "",
        metadata_changed_at=metadata_changed_at if metadata_changed_at is not None else current_entry.get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=metadata_revision if metadata_revision is not None else current_entry.get(METADATA_REVISION_RECORD_KEY),
        writer_id=metadata_writer_id if metadata_writer_id is not None else current_entry.get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=metadata_writer_version if metadata_writer_version is not None else current_entry.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    metadata_map[parameter_key] = {
        "group": _normalize_group_name(next_payload.get("group") or ""),
        METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(next_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
        METADATA_REVISION_RECORD_KEY: _metadata_revision_value(next_payload.get(METADATA_REVISION_RECORD_KEY)),
        METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(next_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
        METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
    }
    map_ok = _write_document_metadata_map(design, metadata_map)
    item_ok = _write_document_metadata_item_entry(
        design,
        parameter_key,
        next_payload.get("group") or "",
        next_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
        next_payload.get(METADATA_REVISION_RECORD_KEY),
        next_payload.get(METADATA_WRITER_ID_RECORD_KEY),
        next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    return bool(map_ok or item_ok)


def _set_document_metadata_entry_with_diagnostics(
    design,
    parameter,
    group_name=None,
    metadata_changed_at=None,
    metadata_revision=None,
    metadata_writer_id=None,
    metadata_writer_version=None,
):
    details = {
        "ok": False,
        "mapOk": False,
        "itemOk": False,
        "errors": [],
        "ownerTypes": [],
    }
    if not design or not parameter:
        details["errors"].append("missing design or parameter")
        return details

    parameter_key = _parameter_entity_token(parameter)
    if not parameter_key:
        details["errors"].append("missing parameter entity token")
        return details

    owners = _document_metadata_owner_candidates(design)
    details["ownerTypes"] = [_owner_debug_label(owner) for owner in owners]
    if not owners:
        details["errors"].append("no document metadata owner candidates")

    metadata_map = _read_document_metadata_map(design)
    current_entry = metadata_map.get(parameter_key) if isinstance(metadata_map.get(parameter_key), dict) else {}
    next_payload = _normalized_metadata_payload(
        group_name=group_name if group_name is not None else current_entry.get("group") or "",
        metadata_changed_at=metadata_changed_at if metadata_changed_at is not None else current_entry.get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=metadata_revision if metadata_revision is not None else current_entry.get(METADATA_REVISION_RECORD_KEY),
        writer_id=metadata_writer_id if metadata_writer_id is not None else current_entry.get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=metadata_writer_version if metadata_writer_version is not None else current_entry.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    metadata_map[parameter_key] = {
        "group": _normalize_group_name(next_payload.get("group") or ""),
        METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(next_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
        METADATA_REVISION_RECORD_KEY: _metadata_revision_value(next_payload.get(METADATA_REVISION_RECORD_KEY)),
        METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(next_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
        METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
    }

    map_payload = {}
    for key, value in (metadata_map or {}).items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(value, dict):
            continue
        map_payload[key] = {
            "group": _normalize_group_name(value.get("group") or ""),
            METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(value.get(METADATA_CHANGED_AT_RECORD_KEY)),
        }
    map_serialized = json.dumps(map_payload, separators=(",", ":"), sort_keys=True)
    map_write = _write_document_attribute_with_diagnostics(
        owners,
        ATTRIBUTE_NAMESPACE,
        ATTRIBUTE_DOCUMENT_METADATA_MAP_NAME,
        map_serialized,
    )
    details["mapOk"] = bool(map_write.get("ok"))
    for error in (map_write.get("errors") or []):
        details["errors"].append(f"doc map: {error}")

    item_payload = {
        "k": str(parameter_key),
        "g": _normalize_group_name(next_payload.get("group") or ""),
        "t": _metadata_changed_at_value(next_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
        "r": _metadata_revision_value(next_payload.get(METADATA_REVISION_RECORD_KEY)),
        "w": _metadata_writer_id_value(next_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
        "v": _metadata_writer_version_value(next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
    }
    item_serialized = json.dumps(item_payload, separators=(",", ":"), sort_keys=True)
    item_write = _write_document_attribute_with_diagnostics(
        owners,
        ATTRIBUTE_DOCUMENT_METADATA_ITEM_NAMESPACE,
        _document_metadata_item_name(parameter_key),
        item_serialized,
    )
    details["itemOk"] = bool(item_write.get("ok"))
    for error in (item_write.get("errors") or []):
        details["errors"].append(f"doc item: {error}")

    details["ok"] = bool(details["mapOk"] or details["itemOk"])
    if not details["ok"] and not details["errors"]:
        details["errors"].append("document metadata writes returned false")
    return details


def _document_metadata_item_name(parameter_key):
    return "p_" + hashlib.sha1(str(parameter_key or "").encode("utf-8")).hexdigest()[:30]


def _read_document_metadata_item_entry(design, parameter_key):
    if not design or not parameter_key:
        return {}

    item_name = _document_metadata_item_name(parameter_key)
    best_entry = {}
    best_timestamp = 0
    for owner in _document_metadata_owner_candidates(design):
        attributes = getattr(owner, "attributes", None)
        if attributes is None:
            continue
        try:
            attribute = attributes.itemByName(ATTRIBUTE_DOCUMENT_METADATA_ITEM_NAMESPACE, item_name)
        except Exception:
            attribute = None
        if attribute is None:
            continue
        try:
            payload = json.loads(str(attribute.value or ""))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("k") or "") != str(parameter_key):
            continue
        group_value = _normalize_group_name(payload.get("g") or "")
        changed_at_value = _metadata_changed_at_value(payload.get("t"))
        revision_value = _metadata_revision_value(payload.get("r"))
        writer_id_value = _metadata_writer_id_value(payload.get("w"))
        writer_version_value = _metadata_writer_version_value(payload.get("v"))
        if changed_at_value < best_timestamp:
            continue
        best_entry = {
            "group": group_value,
            METADATA_CHANGED_AT_RECORD_KEY: changed_at_value,
            METADATA_REVISION_RECORD_KEY: revision_value,
            METADATA_WRITER_ID_RECORD_KEY: writer_id_value,
            METADATA_WRITER_VERSION_RECORD_KEY: writer_version_value,
        }
        best_timestamp = changed_at_value
    return best_entry


def _write_document_metadata_item_entry(
    design,
    parameter_key,
    group_name,
    metadata_changed_at,
    metadata_revision=None,
    metadata_writer_id=None,
    metadata_writer_version=None,
):
    if not design or not parameter_key:
        return False

    item_name = _document_metadata_item_name(parameter_key)
    payload = {
        "k": str(parameter_key),
        "g": _normalize_group_name(group_name or ""),
        "t": _metadata_changed_at_value(metadata_changed_at),
        "r": _metadata_revision_value(metadata_revision),
        "w": _metadata_writer_id_value(metadata_writer_id),
        "v": _metadata_writer_version_value(metadata_writer_version),
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    for owner in _document_metadata_owner_candidates(design):
        attributes = getattr(owner, "attributes", None)
        if attributes is None:
            continue
        try:
            attribute = attributes.itemByName(ATTRIBUTE_DOCUMENT_METADATA_ITEM_NAMESPACE, item_name)
        except Exception:
            attribute = None

        if attribute is not None:
            try:
                attribute.value = serialized
                return True
            except Exception:
                pass

        try:
            attributes.add(ATTRIBUTE_DOCUMENT_METADATA_ITEM_NAMESPACE, item_name, serialized)
            return True
        except Exception:
            pass
    return False


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


def _group_sort_key_for_state(group_name):
    normalized = _normalize_group_name(group_name or "")
    if not normalized:
        return ""
    return normalized.casefold()


def _normalized_group_ui_state(value):
    order = []
    collapsed = {}
    if isinstance(value, dict):
        incoming_order = value.get("order")
        if isinstance(incoming_order, list):
            seen = set()
            for raw in incoming_order:
                name = _normalize_group_name(raw or "")
                if not name:
                    continue
                key = _group_sort_key_for_state(name)
                if key in seen:
                    continue
                seen.add(key)
                order.append(name)
        incoming_collapsed = value.get("collapsed")
        if isinstance(incoming_collapsed, dict):
            for key, raw_value in incoming_collapsed.items():
                group_key = str(key or "").strip().casefold()
                if not group_key and str(key or "").strip() != "":
                    continue
                collapsed[group_key] = bool(raw_value)
    return {"order": order, "collapsed": collapsed}


def _normalized_ui_state_record(value):
    record = value if isinstance(value, dict) else {}
    return {
        UI_STATE_REVISION_KEY: _metadata_revision_value(record.get(UI_STATE_REVISION_KEY)),
        UI_STATE_CHANGED_AT_KEY: _metadata_changed_at_value(record.get(UI_STATE_CHANGED_AT_KEY)),
        UI_STATE_WRITER_ID_KEY: _metadata_writer_id_value(record.get(UI_STATE_WRITER_ID_KEY)),
        UI_STATE_WRITER_VERSION_KEY: _metadata_writer_version_value(record.get(UI_STATE_WRITER_VERSION_KEY)),
    }


def _bump_ui_state_record(previous_record=None):
    previous = _normalized_ui_state_record(previous_record)
    return {
        UI_STATE_REVISION_KEY: _metadata_revision_value(previous.get(UI_STATE_REVISION_KEY)) + 1,
        UI_STATE_CHANGED_AT_KEY: _now_metadata_timestamp_ms(),
        UI_STATE_WRITER_ID_KEY: _current_writer_id(),
        UI_STATE_WRITER_VERSION_KEY: _current_writer_version(),
    }


def _collect_parameter_order_from_records(records):
    items = []
    for key, record in (records or {}).items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(record, dict):
            continue
        order_value = record.get("order")
        if not isinstance(order_value, int):
            order_value = 10 ** 9
        items.append((order_value, key.casefold(), key))
    items.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in items]


def _normalized_parameter_order(order_list, valid_keys=None):
    keys = set(valid_keys or [])
    seen = set()
    normalized = []
    if isinstance(order_list, list):
        for raw in order_list:
            key = str(raw or "").strip()
            if not key:
                continue
            if key in seen:
                continue
            if keys and key not in keys:
                continue
            seen.add(key)
            normalized.append(key)
    return normalized


def _apply_parameter_order_to_records(records, order_list):
    if not isinstance(records, dict):
        return records
    valid_keys = list(records.keys())
    preferred = _normalized_parameter_order(order_list, valid_keys)
    preferred_set = set(preferred)
    remaining = [key for key in _collect_parameter_order_from_records(records) if key not in preferred_set]
    final_order = preferred + remaining
    for index, key in enumerate(final_order):
        record = records.get(key)
        if not isinstance(record, dict):
            continue
        record["order"] = index
    return records


def _parameter_group_name(parameter):
    payload = _parameter_metadata_payload(parameter)
    return _normalize_group_name(payload.get("group") or "")


def _parameter_metadata_changed_at(parameter):
    payload = _parameter_metadata_payload(parameter)
    return _metadata_changed_at_value(payload.get(METADATA_CHANGED_AT_RECORD_KEY))


def _parameter_metadata_payload(parameter):
    if not parameter:
        return _normalized_metadata_payload()

    attributes = getattr(parameter, "attributes", None)
    attribute_payload = {}
    if attributes is not None:
        try:
            group_attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_PARAMETER_GROUP_NAME)
        except Exception:
            group_attribute = None
        try:
            changed_at_attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_METADATA_CHANGED_AT_NAME)
        except Exception:
            changed_at_attribute = None
        try:
            revision_attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_METADATA_REVISION_NAME)
        except Exception:
            revision_attribute = None
        try:
            writer_id_attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_METADATA_WRITER_ID_NAME)
        except Exception:
            writer_id_attribute = None
        try:
            writer_version_attribute = attributes.itemByName(ATTRIBUTE_NAMESPACE, ATTRIBUTE_METADATA_WRITER_VERSION_NAME)
        except Exception:
            writer_version_attribute = None

        attribute_payload = _normalized_metadata_payload(
            group_name=group_attribute.value if group_attribute is not None else "",
            metadata_changed_at=changed_at_attribute.value if changed_at_attribute is not None else 0,
            revision=revision_attribute.value if revision_attribute is not None else 0,
            writer_id=writer_id_attribute.value if writer_id_attribute is not None else "",
            writer_version=writer_version_attribute.value if writer_version_attribute is not None else "",
        )

    design = _design()
    document_payload = _document_metadata_entry(design, parameter)
    return _choose_latest_metadata(attribute_payload, document_payload)


def _set_parameter_metadata_changed_at(parameter, metadata_changed_at):
    if not parameter:
        return False

    current_payload = _parameter_metadata_payload(parameter)
    next_payload = _next_metadata_payload(
        current_payload,
        current_payload.get("group") or "",
        metadata_changed_at,
    )
    return _write_parameter_group_name(
        parameter,
        next_payload.get("group") or "",
        next_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
        next_payload,
    )


def _write_parameter_group_name_with_diagnostics(parameter, group_name, metadata_changed_at=None, metadata_payload=None):
    details = {
        "ok": False,
        "parameterName": "",
        "groupName": "",
        "parameterAttributeOk": False,
        "metadataChangedAtAttributeOk": False,
        "documentMetadataOk": False,
        "documentMapOk": False,
        "documentItemOk": False,
        "documentOwnerTypes": [],
        "errors": [],
    }
    if not parameter:
        details["errors"].append("missing parameter")
        return details

    normalized_group = _normalize_group_name(group_name)
    base_payload = _parameter_metadata_payload(parameter)
    if metadata_payload and isinstance(metadata_payload, dict):
        requested_payload = _normalized_metadata_payload(
            group_name=normalized_group,
            metadata_changed_at=metadata_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=metadata_payload.get(METADATA_REVISION_RECORD_KEY),
            writer_id=metadata_payload.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=metadata_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )
    else:
        requested_payload = _next_metadata_payload(base_payload, normalized_group, metadata_changed_at)
    payload = _normalized_metadata_payload(
        group_name=normalized_group,
        metadata_changed_at=requested_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=requested_payload.get(METADATA_REVISION_RECORD_KEY),
        writer_id=requested_payload.get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=requested_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )

    details["groupName"] = normalized_group
    details["parameterName"] = str(getattr(parameter, "name", "") or "")
    attributes = getattr(parameter, "attributes", None)
    success = False

    def _write_attribute(name, value_text):
        if attributes is None:
            return False
        try:
            attr = attributes.itemByName(ATTRIBUTE_NAMESPACE, name)
        except Exception:
            attr = None
        if attr is not None:
            try:
                attr.value = value_text
                return True
            except Exception:
                return False
        try:
            attributes.add(ATTRIBUTE_NAMESPACE, name, value_text)
            return True
        except Exception:
            return False

    if attributes is None:
        details["errors"].append("parameter has no attributes collection")
    else:
        group_ok = _write_attribute(ATTRIBUTE_PARAMETER_GROUP_NAME, _normalize_group_name(payload.get("group") or ""))
        changed_ok = _write_attribute(ATTRIBUTE_METADATA_CHANGED_AT_NAME, str(_metadata_changed_at_value(payload.get(METADATA_CHANGED_AT_RECORD_KEY))))
        revision_ok = _write_attribute(ATTRIBUTE_METADATA_REVISION_NAME, str(_metadata_revision_value(payload.get(METADATA_REVISION_RECORD_KEY))))
        writer_id_ok = _write_attribute(ATTRIBUTE_METADATA_WRITER_ID_NAME, _metadata_writer_id_value(payload.get(METADATA_WRITER_ID_RECORD_KEY)))
        writer_version_ok = _write_attribute(
            ATTRIBUTE_METADATA_WRITER_VERSION_NAME,
            _metadata_writer_version_value(payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
        )
        details["parameterAttributeOk"] = bool(group_ok)
        details["metadataChangedAtAttributeOk"] = bool(changed_ok)
        if not group_ok:
            details["errors"].append("parameter group attribute write failed")
        if not changed_ok:
            details["errors"].append("parameter metadataChangedAt attribute write failed")
        if not revision_ok:
            details["errors"].append("parameter metadataRevision attribute write failed")
        if not writer_id_ok:
            details["errors"].append("parameter metadataWriterId attribute write failed")
        if not writer_version_ok:
            details["errors"].append("parameter metadataWriterVersion attribute write failed")
        if group_ok and changed_ok and revision_ok and writer_id_ok and writer_version_ok:
            success = True

    design = _design()
    doc_write = _set_document_metadata_entry_with_diagnostics(
        design,
        parameter,
        payload.get("group") or "",
        payload.get(METADATA_CHANGED_AT_RECORD_KEY),
        payload.get(METADATA_REVISION_RECORD_KEY),
        payload.get(METADATA_WRITER_ID_RECORD_KEY),
        payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    details["documentMetadataOk"] = bool(doc_write.get("ok"))
    details["documentMapOk"] = bool(doc_write.get("mapOk"))
    details["documentItemOk"] = bool(doc_write.get("itemOk"))
    details["documentOwnerTypes"] = list(doc_write.get("ownerTypes") or [])
    for error in (doc_write.get("errors") or []):
        details["errors"].append(f"doc: {error}")
    if details["documentMetadataOk"]:
        success = True
        if design:
            try:
                _bump_document_metadata_state(design, _collect_document_metadata_payload_by_key(design))
            except Exception:
                pass

    if not normalized_group and not success:
        details["ok"] = False
        return details
    if not normalized_group:
        details["ok"] = True
        return details
    if success:
        details["ok"] = True
        return details
    details["ok"] = False
    if not details["errors"]:
        details["errors"].append("all metadata write paths failed")
    return details


def _write_parameter_group_name(parameter, group_name, metadata_changed_at=None, metadata_payload=None):
    result = _write_parameter_group_name_with_diagnostics(parameter, group_name, metadata_changed_at, metadata_payload)
    return bool(result.get("ok"))


def _collect_document_metadata_payload_by_key(design):
    payload_by_key = {}
    if not design:
        return payload_by_key
    params = design.userParameters
    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue
        parameter_key = _parameter_entity_token(parameter)
        if not parameter_key:
            continue
        payload_by_key[parameter_key] = _parameter_metadata_payload(parameter)
    return payload_by_key


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


def _set_parameter_group_record(
    design,
    parameter,
    group_name,
    metadata_changed_at=None,
    metadata_revision=None,
    metadata_writer_id=None,
    metadata_writer_version=None,
):
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
    existing_payload = _normalized_metadata_payload(
        group_name=existing_record.get("group") or "",
        metadata_changed_at=existing_record.get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=existing_record.get(METADATA_REVISION_RECORD_KEY),
        writer_id=existing_record.get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=existing_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )
    next_payload = _normalized_metadata_payload(
        group_name=group_name,
        metadata_changed_at=metadata_changed_at if metadata_changed_at is not None else existing_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
        revision=metadata_revision if metadata_revision is not None else existing_payload.get(METADATA_REVISION_RECORD_KEY),
        writer_id=metadata_writer_id if metadata_writer_id is not None else existing_payload.get(METADATA_WRITER_ID_RECORD_KEY),
        writer_version=metadata_writer_version if metadata_writer_version is not None else existing_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
    )

    units_manager = design.unitsManager
    records[parameter_key] = {
        "order": order_value,
        "name": str(parameter.name or ""),
        "current_expression": str(existing_record.get("current_expression") or parameter.expression or ""),
        "previous_expression": str(existing_record.get("previous_expression") or ""),
        "current_value": str(existing_record.get("current_value") or _format_parameter_value(parameter, units_manager)),
        "previous_value": str(existing_record.get("previous_value") or ""),
        "group": _normalize_group_name(next_payload.get("group") or ""),
        METADATA_CHANGED_AT_RECORD_KEY: _metadata_changed_at_value(next_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
        METADATA_REVISION_RECORD_KEY: _metadata_revision_value(next_payload.get(METADATA_REVISION_RECORD_KEY)),
        METADATA_WRITER_ID_RECORD_KEY: _metadata_writer_id_value(next_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
        METADATA_WRITER_VERSION_RECORD_KEY: _metadata_writer_version_value(next_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
    }

    _write_document_order_state(
        {
            "documentId": order_state.get("documentId", ""),
            "documentName": order_state.get("documentName", ""),
            "parameters": records,
            "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
            UI_STATE_RECORD_KEY: _normalized_ui_state_record(order_state.get(UI_STATE_RECORD_KEY)),
        }
    )


def _collect_metadata_debug_snapshot():
    design = _design()
    if not design:
        return {
            "document": _active_document_info(),
            "recordCount": 0,
            "rows": [],
        }

    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    document_metadata_state = _read_document_metadata_state(design)
    rows = []
    params = design.userParameters
    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue

        key = _parameter_entity_token(parameter)
        record = records.get(key) if isinstance(records.get(key), dict) else {}
        fusion_payload = _parameter_metadata_payload(parameter)
        doc_entry = _document_metadata_entry(design, parameter)
        json_payload = _normalized_metadata_payload(
            group_name=record.get("group") or "",
            metadata_changed_at=record.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=record.get(METADATA_REVISION_RECORD_KEY),
            writer_id=record.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=record.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )

        fusion_group = _normalize_group_name(fusion_payload.get("group") or "")
        fusion_changed_at = _metadata_changed_at_value(fusion_payload.get(METADATA_CHANGED_AT_RECORD_KEY))
        json_group = _normalize_group_name(json_payload.get("group") or "")
        json_changed_at = _metadata_changed_at_value(json_payload.get(METADATA_CHANGED_AT_RECORD_KEY))

        latest_source = "equal"
        if _is_metadata_newer(fusion_payload, json_payload):
            latest_source = "fusion"
        elif _is_metadata_newer(json_payload, fusion_payload):
            latest_source = "json"

        rows.append(
            {
                "name": str(parameter.name or ""),
                "key": key,
                "fusionGroup": fusion_group,
                "fusionMetadataChangedAt": fusion_changed_at,
                "fusionMetadataRevision": _metadata_revision_value(fusion_payload.get(METADATA_REVISION_RECORD_KEY)),
                "fusionMetadataWriterId": _metadata_writer_id_value(fusion_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
                "fusionMetadataWriterVersion": _metadata_writer_version_value(fusion_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
                "fusionParameterGroup": _normalize_group_name(fusion_payload.get("group") or ""),
                "fusionParameterMetadataChangedAt": _metadata_changed_at_value(fusion_payload.get(METADATA_CHANGED_AT_RECORD_KEY)),
                "fusionDocumentGroup": _normalize_group_name(doc_entry.get("group") or ""),
                "fusionDocumentMetadataChangedAt": _metadata_changed_at_value(doc_entry.get(METADATA_CHANGED_AT_RECORD_KEY)),
                "jsonGroup": json_group,
                "jsonMetadataChangedAt": json_changed_at,
                "jsonMetadataRevision": _metadata_revision_value(json_payload.get(METADATA_REVISION_RECORD_KEY)),
                "jsonMetadataWriterId": _metadata_writer_id_value(json_payload.get(METADATA_WRITER_ID_RECORD_KEY)),
                "jsonMetadataWriterVersion": _metadata_writer_version_value(json_payload.get(METADATA_WRITER_VERSION_RECORD_KEY)),
                "latestSource": latest_source,
            }
        )

    rows.sort(key=lambda item: item.get("name", "").casefold())
    return {
        "document": _active_document_info(),
        "recordCount": len(records),
        "docMeta": document_metadata_state,
        "rows": rows,
    }


def _sync_metadata_json_to_fusion():
    design = _require_design()
    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    params = design.userParameters
    updated = 0
    skipped = 0
    failed = 0
    failed_names = []
    failed_details = []

    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue

        key = _parameter_entity_token(parameter)
        record = records.get(key) if isinstance(records.get(key), dict) else None
        if not record:
            skipped += 1
            continue

        json_payload = _normalized_metadata_payload(
            group_name=record.get("group") or "",
            metadata_changed_at=record.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=record.get(METADATA_REVISION_RECORD_KEY),
            writer_id=record.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=record.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )
        fusion_payload = _parameter_metadata_payload(parameter)
        if not _is_metadata_newer(json_payload, fusion_payload):
            skipped += 1
            continue

        write_result = _write_parameter_group_name_with_diagnostics(
            parameter,
            json_payload.get("group") or "",
            json_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
            json_payload,
        )
        if write_result.get("ok"):
            updated += 1
        else:
            failed += 1
            failed_names.append(str(parameter.name or key or ""))
            if len(failed_details) < 10:
                errors = write_result.get("errors") or []
                failed_details.append(
                    {
                        "name": str(parameter.name or key or ""),
                        "group": json_payload.get("group") or "",
                        "errors": errors[:5],
                        "documentOwnerTypes": write_result.get("documentOwnerTypes") or [],
                        "parameterAttributeOk": bool(write_result.get("parameterAttributeOk")),
                        "metadataChangedAtAttributeOk": bool(write_result.get("metadataChangedAtAttributeOk")),
                        "documentMapOk": bool(write_result.get("documentMapOk")),
                        "documentItemOk": bool(write_result.get("documentItemOk")),
                    }
                )

    if updated or failed:
        _write_document_order_state(
            {
                "documentId": order_state.get("documentId", ""),
                "documentName": order_state.get("documentName", ""),
                "parameters": records,
                "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
                UI_STATE_RECORD_KEY: _normalized_ui_state_record(order_state.get(UI_STATE_RECORD_KEY)),
            }
        )
    _bump_document_metadata_state(design, _collect_document_metadata_payload_by_key(design))

    return {
        "direction": "json_to_fusion",
        "updatedCount": updated,
        "skippedCount": skipped,
        "failedCount": failed,
        "failedNames": failed_names[:20],
        "failedDetails": failed_details,
    }


def _sync_metadata_fusion_to_json():
    design = _require_design()
    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    params = design.userParameters
    updated = 0
    skipped = 0

    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue

        parameter_key = _parameter_entity_token(parameter)
        json_record = records.get(parameter_key) if isinstance(records.get(parameter_key), dict) else {}
        json_payload = _normalized_metadata_payload(
            group_name=json_record.get("group") or "",
            metadata_changed_at=json_record.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=json_record.get(METADATA_REVISION_RECORD_KEY),
            writer_id=json_record.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=json_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )
        fusion_payload = _parameter_metadata_payload(parameter)
        if not _is_metadata_newer(fusion_payload, json_payload):
            skipped += 1
            continue
        _set_parameter_group_record(
            design,
            parameter,
            fusion_payload.get("group") or "",
            fusion_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
            fusion_payload.get(METADATA_REVISION_RECORD_KEY),
            fusion_payload.get(METADATA_WRITER_ID_RECORD_KEY),
            fusion_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )
        updated += 1

    return {
        "direction": "fusion_to_json",
        "updatedCount": updated,
        "skippedCount": skipped,
    }


def _repair_metadata():
    design = _require_design()
    order_state = _read_document_order_state()
    records = _resolve_document_order_records(design, order_state.get("parameters") or {})
    params = design.userParameters

    updated_fusion = 0
    updated_json = 0
    healed = 0
    conflicts = 0
    failed = 0
    failed_names = []

    for index in range(params.count):
        parameter = params.item(index)
        if not parameter:
            continue
        key = _parameter_entity_token(parameter)
        if not key:
            continue

        json_record = records.get(key) if isinstance(records.get(key), dict) else {}
        json_payload = _normalized_metadata_payload(
            group_name=json_record.get("group") or "",
            metadata_changed_at=json_record.get(METADATA_CHANGED_AT_RECORD_KEY),
            revision=json_record.get(METADATA_REVISION_RECORD_KEY),
            writer_id=json_record.get(METADATA_WRITER_ID_RECORD_KEY),
            writer_version=json_record.get(METADATA_WRITER_VERSION_RECORD_KEY),
        )
        fusion_payload = _parameter_metadata_payload(parameter)

        json_missing = not json_record
        fusion_missing = not _normalize_group_name(fusion_payload.get("group") or "")
        winner_payload = _choose_latest_metadata(fusion_payload, json_payload)

        if json_missing or fusion_missing:
            healed += 1
        if _is_metadata_newer(fusion_payload, json_payload) and _is_metadata_newer(json_payload, fusion_payload):
            conflicts += 1

        if _is_metadata_newer(winner_payload, fusion_payload):
            write_result = _write_parameter_group_name_with_diagnostics(
                parameter,
                winner_payload.get("group") or "",
                winner_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
                winner_payload,
            )
            if write_result.get("ok"):
                updated_fusion += 1
            else:
                failed += 1
                failed_names.append(str(parameter.name or key or ""))

        if _is_metadata_newer(winner_payload, json_payload) or json_missing:
            _set_parameter_group_record(
                design,
                parameter,
                winner_payload.get("group") or "",
                winner_payload.get(METADATA_CHANGED_AT_RECORD_KEY),
                winner_payload.get(METADATA_REVISION_RECORD_KEY),
                winner_payload.get(METADATA_WRITER_ID_RECORD_KEY),
                winner_payload.get(METADATA_WRITER_VERSION_RECORD_KEY),
            )
            updated_json += 1

    if updated_json:
        order_state = _read_document_order_state()
        records = _resolve_document_order_records(design, order_state.get("parameters") or {})
        _write_document_order_state(
            {
                "documentId": order_state.get("documentId", ""),
                "documentName": order_state.get("documentName", ""),
                "parameters": records,
                "groupUi": order_state.get("groupUi", {"order": [], "collapsed": {}}),
                UI_STATE_RECORD_KEY: _normalized_ui_state_record(order_state.get(UI_STATE_RECORD_KEY)),
            }
        )
    _bump_document_metadata_state(design, _collect_document_metadata_payload_by_key(design))

    return {
        "direction": "repair",
        "updatedFusionCount": updated_fusion,
        "updatedJsonCount": updated_json,
        "healedCount": healed,
        "conflictCount": conflicts,
        "failedCount": failed,
        "failedNames": failed_names[:20],
        "updatedCount": updated_fusion + updated_json,
        "skippedCount": 0,
    }


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


# REVIEW: _release_notes_html is defined but not called anywhere in this file.
# Remove if no caller exists in a future UI that renders HTML release notes.
def _release_notes_html(notes_text):
    import html as _html
    text = _normalized_release_notes(notes_text)
    if not text:
        return ''
    return '<br/>'.join(_html.escape(line) if line.strip() else '' for line in text.split('\n'))


def _background_update_check():
    """Fetch latest release info at startup in a background thread.

    No Fusion API calls here — only file I/O and network. All exceptions
    are swallowed so a network failure never blocks or breaks add-in loading.
    """
    try:
        settings = _load_settings()
        if not bool(settings.get("autoCheckUpdates", True)):
            return
        cached = _normalized_update_check(settings.get("updateCheck") or {})
        checked_at = cached.get("checked_at", 0)
        is_fresh = bool(checked_at and (time.time() - checked_at) < UPDATE_CACHE_MAX_AGE_SECONDS)
        if is_fresh:
            return
        latest = _fetch_latest_release_info()
        _save_update_check(latest)
    except Exception:
        pass


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
        shutil.copyfileobj(response, handle)


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
            raw_name = str(member.filename or '')
            normalized_name = raw_name.replace('\\', '/').strip('/')
            if not normalized_name:
                continue

            parts = [part for part in normalized_name.split('/') if part not in {'', '.', '..'}]
            if not parts:
                continue

            destination = os.path.join(extract_root, *parts)
            is_directory = bool(
                member.is_dir()
                or raw_name.endswith('/')
                or raw_name.endswith('\\')
                or str(member.filename or '').replace('\\', '/').endswith('/')
            )
            if is_directory:
                if os.path.exists(destination) and not os.path.isdir(destination):
                    os.remove(destination)
                os.makedirs(destination, exist_ok=True)
                continue

            parent_dir = os.path.dirname(destination)
            if os.path.exists(parent_dir) and not os.path.isdir(parent_dir):
                os.remove(parent_dir)
            os.makedirs(parent_dir, exist_ok=True)
            if os.path.isdir(destination):
                shutil.rmtree(destination, ignore_errors=True)
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
