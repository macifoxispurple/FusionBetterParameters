"""Fusion in-process test harness for BetterParameters backend actions.

Run this script directly inside Fusion 360 (Scripts and Add-Ins -> Scripts).
It executes a focused action-level regression flow against BetterParameters.py:
- contract info probe
- test parameter seed/reset
- M3 action checks (copy/delete/timeline sort)
- dependency graph checks
- CSV export/import/dry-run/conflict-policy checks
- BP package export + dry-run import checks
- sequential update checks used by FE Apply-All behavior
- backend self-test suite smoke run

This harness calls BetterParameters' internal action dispatcher (`_handle_palette_action`) to
exercise the same paths used by the palette bridge, without requiring UI interaction.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import platform
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import adsk.core  # type: ignore


def _default_live_addin_bp_path() -> str:
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(
            appdata,
            "Autodesk",
            "Autodesk Fusion 360",
            "API",
            "AddIns",
            "BetterParameters",
            "BetterParameters.py",
        )
    if system == "Darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/BetterParameters/BetterParameters.py"
        )
    return ""


def _log(message: str) -> None:
    app = adsk.core.Application.get()
    if app:
        app.log(f"[BP Harness] {message}")


def _message_box(message: str, title: str = "BetterParameters Harness") -> None:
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
    if ui:
        ui.messageBox(message, title)


def _candidate_bp_paths() -> List[str]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_override = str(os.environ.get("BP_HARNESS_BP_PATH") or "").strip()
    repo_bp_path = os.path.normpath(os.path.join(script_dir, "..", "BetterParameters", "BetterParameters.py"))
    local_peer_path = os.path.join(script_dir, "BetterParameters.py")
    live_addin_path = _default_live_addin_bp_path()
    return [env_override, repo_bp_path, live_addin_path, local_peer_path]


def _load_bp_module() -> Any:
    existing = sys.modules.get("BetterParameters")
    if existing is not None:
        _log("Using loaded BetterParameters module from sys.modules.")
        return existing

    for path in _candidate_bp_paths():
        if not path or not os.path.isfile(path):
            continue
        spec = importlib.util.spec_from_file_location("BetterParameters", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules["BetterParameters"] = module
        spec.loader.exec_module(module)
        _log(f"Loaded BetterParameters module from: {path}")
        return module

    raise RuntimeError(
        "Could not locate BetterParameters.py. Checked: " + ", ".join(_candidate_bp_paths())
    )


def _bootstrap_bp_runtime_globals(bp: Any) -> None:
    """Initialize BetterParameters module globals needed by action handlers.

    In Fusion script context, BetterParameters.run(...) is not guaranteed to have
    executed, so module globals (`app`, `ui`) may still be null-casts.
    """
    app = adsk.core.Application.get()
    if app is None:
        raise RuntimeError("Fusion application is not available.")
    try:
        bp.app = app
    except Exception:
        pass
    try:
        bp.ui = app.userInterface
    except Exception:
        pass


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class HarnessState:
    results: List[TestResult] = field(default_factory=list)
    temp_files: List[str] = field(default_factory=list)

    def add_result(self, name: str, passed: bool, detail: str = "") -> None:
        self.results.append(TestResult(name=name, passed=passed, detail=detail))

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)


def _assert_true(state: HarnessState, name: str, condition: bool, detail: str = "") -> None:
    state.add_result(name, bool(condition), detail if not condition else "")


def _call_action(bp: Any, action: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = payload or {}
    _log(f"Action -> {action} {json.dumps(data, ensure_ascii=True)}")
    response = bp._handle_palette_action(action, data)  # pylint: disable=protected-access
    if not isinstance(response, dict):
        raise RuntimeError(f"Action {action} returned non-dict response: {type(response)}")
    _log(f"Action <- {action} ok={response.get('ok')} msg={response.get('message', '')}")
    return response


def _ensure_design_open(bp: Any) -> Tuple[bool, str, Any]:
    app = adsk.core.Application.get()
    if not app:
        return False, "Fusion application is not available.", None

    def _resolve_design() -> Any:
        try:
            if hasattr(bp, "_design"):
                return bp._design()  # pylint: disable=protected-access
        except Exception:
            return None
        return None

    design = _resolve_design()
    if design:
        return True, "", design

    # Auto-open a design document when the active product is not a Design.
    try:
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    except Exception as exc:
        product = getattr(app, "activeProduct", None)
        product_type = getattr(product, "objectType", type(product).__name__) if product is not None else "None"
        return False, f"No active Fusion Design. activeProduct={product_type}; auto-open failed: {exc}", None

    design = _resolve_design()
    if design:
        return True, "", design

    product = getattr(app, "activeProduct", None)
    product_type = getattr(product, "objectType", type(product).__name__) if product is not None else "None"
    return False, f"No active Fusion Design after auto-open attempt. activeProduct={product_type}", None


def _find_param(design: Any, name: str) -> Any:
    params = design.userParameters
    return params.itemByName(name)


def _create_temp_csv(state: HarnessState) -> str:
    fd, path = tempfile.mkstemp(prefix="bp_harness_", suffix=".csv", text=True)
    os.close(fd)
    state.temp_files.append(path)

    rows = [
        ["name", "expression", "unit", "comment", "group"],
        ["_bptest_csv_harness_a", "15 mm", "mm", "", "HarnessGroup"],
        ["_bptest_csv_harness_b", "_bptest_csv_harness_a * 2", "mm", "", "HarnessGroup"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    return path


def _create_temp_csv_rows(state: HarnessState, rows: List[List[str]]) -> str:
    fd, path = tempfile.mkstemp(prefix="bp_harness_", suffix=".csv", text=True)
    os.close(fd)
    state.temp_files.append(path)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    return path


def _create_temp_bpmeta_path(state: HarnessState) -> str:
    fd, path = tempfile.mkstemp(prefix="bp_harness_", suffix=".bpmeta.json", text=True)
    os.close(fd)
    state.temp_files.append(path)
    return path


def _cleanup_files(state: HarnessState) -> None:
    for path in state.temp_files:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as exc:  # pragma: no cover
            _log(f"Cleanup warning for {path}: {exc}")


def _copy_to_clipboard(text: str) -> Tuple[bool, str]:
    """Best-effort clipboard copy with verification."""
    if not text:
        return False, "No text to copy."
    system = platform.system()

    if system == "Darwin":
        try:
            write_cmd = subprocess.run(
                ["pbcopy"],
                input=text,
                text=True,
                capture_output=True,
                check=False,
            )
            if write_cmd.returncode != 0:
                err = (write_cmd.stderr or write_cmd.stdout or "").strip()
                return False, err or f"pbcopy exited with code {write_cmd.returncode}"
            read_cmd = subprocess.run(
                ["pbpaste"],
                text=True,
                capture_output=True,
                check=False,
            )
            echoed = read_cmd.stdout or ""
            if read_cmd.returncode == 0 and echoed == text:
                return True, ""
            return False, "Clipboard verify mismatch after pbcopy write."
        except Exception as exc:
            return False, str(exc)

    if os.name != "nt":
        return False, f"Clipboard auto-copy not implemented for OS: {system}"

    # Primary path: PowerShell Set-Clipboard + Get-Clipboard verification.
    try:
        ps_script = (
            "$inputData = [Console]::In.ReadToEnd(); "
            "Set-Clipboard -Value $inputData; "
            "$echo = Get-Clipboard -Raw; "
            "if ($echo -eq $inputData) { Write-Output 'OK' } else { Write-Output 'MISMATCH' }"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            input=text,
            text=True,
            capture_output=True,
            check=False,
        )
        out = (completed.stdout or "").strip()
        if completed.returncode == 0 and out == "OK":
            return True, ""
    except Exception:
        pass

    # Fallback path: clip.exe, then verify using Get-Clipboard.
    try:
        completed = subprocess.run(
            ["clip"],
            input=text,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "").strip()
            return False, err or f"clip exited with code {completed.returncode}"
        verify = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"],
            text=True,
            capture_output=True,
            check=False,
        )
        echoed = verify.stdout or ""
        if verify.returncode == 0 and echoed == text:
            return True, ""
        return False, "Clipboard verify mismatch after clip.exe write."
    except Exception as exc:
        return False, str(exc)


def _write_report_file(summary: str) -> Tuple[bool, str]:
    """Write summary to a timestamped report file."""
    try:
        override = str(os.environ.get("BP_HARNESS_REPORT_DIR") or "").strip()
        if override:
            out_dir = Path(override).expanduser().resolve()
        else:
            root = Path(__file__).resolve().parents[1]
            out_dir = root / "_harness_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"fusion_bp_harness_{stamp}.txt"
        out_path.write_text(summary, encoding="utf-8")
        return True, str(out_path)
    except Exception as exc:
        return False, str(exc)


def _state_user_params(state_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    params = state_payload.get("userParameters") if isinstance(state_payload, dict) else []
    return params if isinstance(params, list) else []


def _state_param_by_name(state_payload: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    for row in _state_user_params(state_payload):
        if str(row.get("name", "")) == name:
            return row
    return None


def _expr_norm(expr: str) -> str:
    return "".join(str(expr or "").split()).lower()


def _run_harness() -> HarnessState:
    state = HarnessState()
    bp = _load_bp_module()
    _bootstrap_bp_runtime_globals(bp)

    ok_design, design_message, design = _ensure_design_open(bp)
    if not ok_design:
        _assert_true(state, "design/open", False, design_message)
        return state

    app = adsk.core.Application.get()
    assert app is not None
    assert design is not None

    # Baseline cleanup first.
    try:
        reset_resp = _call_action(bp, "resetTestState", {"confirm": "RESET"})
        _assert_true(state, "reset/pre", bool(reset_resp.get("ok")), reset_resp.get("message", ""))
    except Exception as exc:
        _assert_true(state, "reset/pre", False, str(exc))

    try:
        contract = _call_action(bp, "getBackendContractInfo", {})
        _assert_true(state, "contract/ok", bool(contract.get("ok")), contract.get("message", ""))
        _assert_true(state, "contract/state-null", contract.get("state") is None, "state should be null")
        actions = contract.get("actions") or {}
        _assert_true(state, "contract/actions-readonly", isinstance(actions.get("readOnly"), list))
        _assert_true(state, "contract/actions-mutating", isinstance(actions.get("mutating"), list))
    except Exception as exc:
        _assert_true(state, "contract/exception", False, str(exc))

    try:
        seed_resp = _call_action(
            bp,
            "seedTestParameters",
            {
                "parameters": [
                    {"name": "width", "expression": "10 mm", "unit": "mm", "group": "HarnessGroup"},
                    {
                        "name": "height",
                        "expression": "_bptest_width * 2",
                        "unit": "mm",
                        "comment": "",
                        "group": "HarnessGroup",
                    },
                ]
            },
        )
        _assert_true(state, "seed/ok", bool(seed_resp.get("ok")), seed_resp.get("message", ""))
        _assert_true(state, "seed/count", int(seed_resp.get("seededCount", 0)) >= 2, "expected >=2 seeded")
    except Exception as exc:
        _assert_true(state, "seed/exception", False, str(exc))

    try:
        seed_state = seed_resp.get("state") if isinstance(seed_resp, dict) else {}
        width_row = _state_param_by_name(seed_state, "_bptest_width")
        width_key = str((width_row or {}).get("key") or "").strip()
        if not width_key:
            width_param = _find_param(design, "_bptest_width")
            width_key = str(getattr(width_param, "entityToken", "") or "").strip()
        _assert_true(state, "m3/copy/key-present", bool(width_key), "could not resolve _bptest_width token")

        # Provide both key and name so backend can still resolve reliably if token lookup
        # is temporarily unavailable in a given Fusion runtime context.
        copy_auto = _call_action(bp, "copyParameter", {"key": width_key, "name": "_bptest_width"})
        _assert_true(state, "m3/copy/auto-ok", bool(copy_auto.get("ok")), copy_auto.get("message", ""))
        copied_auto = _find_param(design, "_bptest_width_copy")
        _assert_true(state, "m3/copy/auto-created", copied_auto is not None, "expected _bptest_width_copy")

        copy_named = _call_action(
            bp,
            "copyParameter",
            {"name": "_bptest_height", "targetName": "_bptest_height_clone"},
        )
        _assert_true(state, "m3/copy/named-ok", bool(copy_named.get("ok")), copy_named.get("message", ""))
        copied_named = _find_param(design, "_bptest_height_clone")
        _assert_true(state, "m3/copy/named-created", copied_named is not None, "expected _bptest_height_clone")

        delete_partial = _call_action(
            bp,
            "deleteParameters",
            {"names": ["_bptest_height_clone", "_bptest_missing_delete_target"]},
        )
        _assert_true(state, "m3/delete/partial-ok", bool(delete_partial.get("ok")), delete_partial.get("message", ""))
        _assert_true(
            state,
            "m3/delete/partial-count",
            int(delete_partial.get("deletedCount", 0)) == 1 and int(delete_partial.get("failedCount", 0)) >= 1,
            f"deleted={delete_partial.get('deletedCount')} failed={delete_partial.get('failedCount')}",
        )
        deleted_clone = _find_param(design, "_bptest_height_clone")
        _assert_true(state, "m3/delete/removed", deleted_clone is None, "clone should be deleted")

        timeline_seed = _call_action(
            bp,
            "seedTestParameters",
            {
                "parameters": [
                    {"name": "timeline_c", "expression": "3 mm", "unit": "mm"},
                    {"name": "timeline_a", "expression": "1 mm", "unit": "mm"},
                    {"name": "timeline_b", "expression": "2 mm", "unit": "mm"},
                ]
            },
        )
        _assert_true(state, "m3/timeline/seed-ok", bool(timeline_seed.get("ok")), timeline_seed.get("message", ""))

        timeline_sort = _call_action(bp, "sortByTimelineOrder", {})
        _assert_true(state, "m3/timeline/sort-ok", bool(timeline_sort.get("ok")), timeline_sort.get("message", ""))
        # Prefer authoritative Fusion order directly from design.userParameters.
        # Some state payload variants can omit these rows from userParameters slice.
        design_names = []
        params = design.userParameters
        for i in range(params.count):
            p = params.item(i)
            if p:
                design_names.append(str(getattr(p, "name", "") or ""))
        idx_c = design_names.index("_bptest_timeline_c") if "_bptest_timeline_c" in design_names else -1
        idx_a = design_names.index("_bptest_timeline_a") if "_bptest_timeline_a" in design_names else -1
        idx_b = design_names.index("_bptest_timeline_b") if "_bptest_timeline_b" in design_names else -1

        # Fallback to returned state ordering only when direct design lookup fails.
        if idx_c < 0 or idx_a < 0 or idx_b < 0:
            sorted_state = timeline_sort.get("state") if isinstance(timeline_sort.get("state"), dict) else {}
            sorted_names = [str(p.get("name", "")) for p in _state_user_params(sorted_state)]
            idx_c = sorted_names.index("_bptest_timeline_c") if "_bptest_timeline_c" in sorted_names else -1
            idx_a = sorted_names.index("_bptest_timeline_a") if "_bptest_timeline_a" in sorted_names else -1
            idx_b = sorted_names.index("_bptest_timeline_b") if "_bptest_timeline_b" in sorted_names else -1
        _assert_true(
            state,
            "m3/timeline/order-cab",
            idx_c >= 0 and idx_a > idx_c and idx_b > idx_a,
            f"indices c/a/b={idx_c}/{idx_a}/{idx_b}",
        )
    except Exception as exc:
        _assert_true(state, "m3/actions-exception", False, str(exc))

    try:
        graph_resp = _call_action(bp, "getParameterDependencyGraph", {})
        _assert_true(state, "graph/ok", bool(graph_resp.get("ok")), graph_resp.get("message", ""))
        _assert_true(state, "graph/state-null", graph_resp.get("state") is None, "state should be null")
        nodes = graph_resp.get("nodes") or []
        edges = graph_resp.get("edges") or []
        node_names = {str(node.get("name", "")) for node in nodes}
        _assert_true(state, "graph/node-width", "_bptest_width" in node_names)
        _assert_true(state, "graph/node-height", "_bptest_height" in node_names)
        has_edge = any((edge.get("from") == "_bptest_height" and edge.get("to") == "_bptest_width") for edge in edges)
        _assert_true(state, "graph/edge-height-width", has_edge)
    except Exception as exc:
        _assert_true(state, "graph/exception", False, str(exc))

    csv_path = _create_temp_csv(state)
    try:
        export_csv_path = _create_temp_csv_rows(state, [["name", "expression", "unit", "comment", "group"]])
        export_csv = _call_action(bp, "exportParameters", {"filePath": export_csv_path})
        _assert_true(state, "csv-export/ok", bool(export_csv.get("ok")), export_csv.get("message", ""))
        _assert_true(state, "csv-export/file", os.path.isfile(export_csv_path), "csv file missing after export")
        exported_text = ""
        if os.path.isfile(export_csv_path):
            exported_text = Path(export_csv_path).read_text(encoding="utf-8-sig")
        _assert_true(
            state,
            "csv-export/header",
            exported_text.splitlines()[0].strip().lower() == "name,expression,unit,comment,group" if exported_text else False,
            "csv header mismatch",
        )

        dry_csv = _call_action(bp, "importParameters", {"filePath": csv_path, "conflictPolicy": "overwrite", "dryRun": True})
        _assert_true(state, "csv-dry/ok", bool(dry_csv.get("ok")), dry_csv.get("message", ""))
        _assert_true(state, "csv-dry/state-null", dry_csv.get("state") is None, "state should be null on dryRun")
        _assert_true(state, "csv-dry/flag", dry_csv.get("dryRun") is True, "dryRun echo should be true")

        dry_created = _find_param(design, "_bptest_csv_harness_a")
        _assert_true(state, "csv-dry/no-mutation", dry_created is None, "parameter should not exist after dryRun")

        commit_csv = _call_action(bp, "importParameters", {"filePath": csv_path, "conflictPolicy": "overwrite", "dryRun": False})
        _assert_true(state, "csv-commit/ok", bool(commit_csv.get("ok")), commit_csv.get("message", ""))
        committed = _find_param(design, "_bptest_csv_harness_a")
        _assert_true(state, "csv-commit/mutated", committed is not None, "expected created parameter after commit")

        conflict_rows = [
            ["name", "expression", "unit", "comment", "group"],
            ["_bptest_width", "99 mm", "mm", "", "HarnessGroup"],
            ["_bptest_conflict_new", "7 mm", "mm", "", "HarnessGroup"],
        ]
        conflict_path = _create_temp_csv_rows(state, conflict_rows)

        skip_resp = _call_action(bp, "importParameters", {"filePath": conflict_path, "conflictPolicy": "skip", "dryRun": False})
        _assert_true(state, "csv-policy-skip/ok", bool(skip_resp.get("ok")), skip_resp.get("message", ""))
        width_after_skip = _find_param(design, "_bptest_width")
        width_skip_expr = str(width_after_skip.expression) if width_after_skip else ""
        _assert_true(
            state,
            "csv-policy-skip/no-overwrite",
            _expr_norm(width_skip_expr) == _expr_norm("10 mm"),
            f"width expression became {width_skip_expr!r}",
        )
        new_after_skip = _find_param(design, "_bptest_conflict_new")
        _assert_true(state, "csv-policy-skip/new-created", new_after_skip is not None, "new param should be created with skip")

        overwrite_resp = _call_action(
            bp,
            "importParameters",
            {"filePath": conflict_path, "conflictPolicy": "overwrite", "dryRun": False},
        )
        _assert_true(state, "csv-policy-overwrite/ok", bool(overwrite_resp.get("ok")), overwrite_resp.get("message", ""))
        width_after_overwrite = _find_param(design, "_bptest_width")
        width_overwrite_expr = str(width_after_overwrite.expression) if width_after_overwrite else ""
        _assert_true(
            state,
            "csv-policy-overwrite/did-overwrite",
            _expr_norm(width_overwrite_expr) == _expr_norm("99 mm"),
            f"width expression is {width_overwrite_expr!r}",
        )

        # Action-level check that FE Apply-All sequential pattern is viable:
        # each update returns state and later expressions can reference earlier updates.
        width_key = str(width_after_overwrite.entityToken) if width_after_overwrite else ""
        update_width = _call_action(
            bp,
            "updateParameter",
            {"key": width_key, "name": "_bptest_width", "expression": "12 mm"},
        )
        _assert_true(state, "m4/update-seq/step1-ok", bool(update_width.get("ok")), update_width.get("message", ""))
        _assert_true(state, "m4/update-seq/step1-state", isinstance(update_width.get("state"), dict), "expected state dict")
        update_height = _call_action(
            bp,
            "updateParameter",
            {"name": "_bptest_height", "expression": "_bptest_width * 3"},
        )
        _assert_true(state, "m4/update-seq/step2-ok", bool(update_height.get("ok")), update_height.get("message", ""))
        _assert_true(state, "m4/update-seq/step2-state", isinstance(update_height.get("state"), dict), "expected state dict")
        height_after_seq = _find_param(design, "_bptest_height")
        height_seq_expr = str(height_after_seq.expression) if height_after_seq else ""
        _assert_true(
            state,
            "m4/update-seq/step2-expression",
            _expr_norm(height_seq_expr) == _expr_norm("_bptest_width * 3"),
            f"height expression is {height_seq_expr!r}",
        )
    except Exception as exc:
        _assert_true(state, "csv/import-exception", False, str(exc))

    # batchUpdateParameters — single Fusion call, single recompute.
    try:
        # Requires _bptest_width and _bptest_height to exist from the CSV import above.
        width_param = _find_param(design, "_bptest_width")
        height_param = _find_param(design, "_bptest_height")
        width_key  = str(width_param.entityToken)  if width_param  else ""
        height_key = str(height_param.entityToken) if height_param else ""
        batch_resp = _call_action(bp, "batchUpdateParameters", {
            "updates": [
                {"key": width_key,  "name": "_bptest_width",  "expression": "77 mm", "comment": "batch-w"},
                {"key": height_key, "name": "_bptest_height", "expression": "33 mm", "comment": "batch-h"},
            ]
        })
        _assert_true(state, "batch/ok",    bool(batch_resp.get("ok")),                  batch_resp.get("message", ""))
        _assert_true(state, "batch/state", isinstance(batch_resp.get("state"), dict),   "expected state dict")
        _assert_true(state, "batch/count", int(batch_resp.get("updatedCount", 0)) == 2, f"updatedCount={batch_resp.get('updatedCount')}")
        width_after_batch  = _find_param(design, "_bptest_width")
        height_after_batch = _find_param(design, "_bptest_height")
        w_expr = str(width_after_batch.expression)  if width_after_batch  else ""
        h_expr = str(height_after_batch.expression) if height_after_batch else ""
        _assert_true(state, "batch/width-expr",  _expr_norm(w_expr) == _expr_norm("77 mm"), f"width={w_expr!r}")
        _assert_true(state, "batch/height-expr", _expr_norm(h_expr) == _expr_norm("33 mm"), f"height={h_expr!r}")
    except Exception as exc:
        _assert_true(state, "batch/exception", False, str(exc))

    pkg_path = _create_temp_bpmeta_path(state)
    try:
        export_pkg = _call_action(
            bp,
            "exportParametersPackage",
            {
                "filePath": pkg_path,
                "includeComments": True,
                "includeGroups": True,
                "includeFavorites": True,
                "includeOrder": True,
            },
        )
        _assert_true(state, "pkg-export/ok", bool(export_pkg.get("ok")), export_pkg.get("message", ""))
        _assert_true(state, "pkg-export/file", os.path.isfile(pkg_path), "package file missing after export")

        dry_pkg = _call_action(
            bp,
            "importParametersPackage",
            {
                "filePath": pkg_path,
                "conflictPolicy": "merge-safe",
                "applyExpressionsUnits": True,
                "applyComments": True,
                "applyGroups": True,
                "applyFavorites": True,
                "applyOrder": True,
                "dryRun": True,
            },
        )
        _assert_true(state, "pkg-dry/ok", bool(dry_pkg.get("ok")), dry_pkg.get("message", ""))
        _assert_true(state, "pkg-dry/state-null", dry_pkg.get("state") is None, "state should be null on dryRun")
        _assert_true(state, "pkg-dry/flag", dry_pkg.get("dryRun") is True, "dryRun echo should be true")
    except Exception as exc:
        _assert_true(state, "pkg/exception", False, str(exc))

    try:
        self_tests = _call_action(bp, "runSelfTestSuite", {"filter": "smoke"})
        _assert_true(state, "selftest/ok", bool(self_tests.get("ok")), self_tests.get("message", ""))
        _assert_true(state, "selftest/state-null", self_tests.get("state") is None, "state should be null")
        total_count = int(self_tests.get("totalCount", 0))
        failed_count = int(self_tests.get("failedCount", 0))
        _assert_true(state, "selftest/has-tests", total_count > 0, "expected at least one smoke test")
        _assert_true(state, "selftest/no-failures", failed_count == 0, f"failedCount={failed_count}")
    except Exception as exc:
        _assert_true(state, "selftest/exception", False, str(exc))

    # Required cleanup at end.
    try:
        reset_resp = _call_action(bp, "resetTestState", {"confirm": "RESET"})
        _assert_true(state, "reset/post", bool(reset_resp.get("ok")), reset_resp.get("message", ""))
    except Exception as exc:
        _assert_true(state, "reset/post", False, str(exc))

    _cleanup_files(state)
    return state


def _format_summary(state: HarnessState) -> str:
    lines = []
    lines.append(f"timestamp: {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}")
    lines.append(f"BetterParameters Harness: {state.passed_count} passed, {state.failed_count} failed")
    for result in state.results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        lines.append(f"[{status}] {result.name}{detail}")
    return "\n".join(lines)


def run(_context: Any) -> None:
    try:
        state = _run_harness()
        summary = _format_summary(state)
        report_ok, report_info = _write_report_file(summary)
        copied_ok, copy_info = _copy_to_clipboard(summary)
        header_lines = [
            "BetterParameters Harness",
            f"Clipboard: {'Copied' if copied_ok else f'Not copied ({copy_info})'}",
            f"Report: {report_info if report_ok else f'Not written ({report_info})'}",
            "",
        ]
        full_text = "\n".join(header_lines) + summary
        _log(summary)
        _message_box(full_text)
    except Exception:
        err = traceback.format_exc()
        _log(err)
        _message_box(f"Harness crashed:\n\n{err}")


def stop(_context: Any) -> None:
    _log("Harness stopped.")

