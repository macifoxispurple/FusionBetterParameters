"""Probe using one visible Fusion user parameter as BP metadata storage.

Run inside Fusion 360: Utilities/Scripts and Add-Ins -> Scripts -> Run.

Default behavior uses the active Fusion design, then creates/updates:
- _bp_probe_metadata_v1
- _bp_probe_user_a
- _bp_probe_user_b
- _bp_probe_meta_size
- _bp_probe_real_0001 ... _bp_probe_real_2695

If no Fusion design is active, the script creates a new unsaved test design.

To test save/close/reopen durability:
1. Run this script in the generated test design.
2. Save the design.
3. Close and reopen it.
4. Run this script again and inspect token/comment comparison results.

Durable checkpoint versions use one reusable metadata parameter. Each checkpoint
adds enough simulated real Fusion user parameters to match the rough capacity
estimate for that label, writes compact metadata for real entity tokens, then
saves the document.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import adsk.core  # type: ignore
import adsk.fusion  # type: ignore


PROBE_METADATA_PARAM = "_bp_probe_metadata_v1"
PROBE_USER_PARAMS = ("_bp_probe_user_a", "_bp_probe_user_b")
COMMENT_SIZE_TARGETS = [
    1024,
    4096,
    16 * 1024,
    64 * 1024,
    128 * 1024,
    256 * 1024,
]
DURABLE_COMMENT_SIZE_TARGETS = [
    ("4k", 4 * 1024, 36),
    ("64k", 64 * 1024, 669),
    ("128k", 128 * 1024, 1344),
    ("256k", 256 * 1024, 2695),
]
DURABLE_SINGLE_PARAM = "_bp_probe_meta_size"
SIM_PARAM_PREFIX = "_bp_probe_real_"
SIM_GROUPS = ("Dimensions", "Manufacturing", "Motion", "Electrical", "Reference", "QA")


def _app() -> adsk.core.Application:
    app = adsk.core.Application.get()
    if not app:
        raise RuntimeError("Fusion application is not available.")
    return app


def _ui() -> Optional[adsk.core.UserInterface]:
    app = _app()
    return app.userInterface if app else None


def _log(message: str) -> None:
    try:
        _app().log(f"[BP metadata probe] {message}")
    except Exception:
        pass


def _message(message: str, title: str = "BP Metadata Parameter Probe") -> None:
    ui = _ui()
    if ui:
        ui.messageBox(message, title)


def _active_design() -> Optional[adsk.fusion.Design]:
    try:
        return adsk.fusion.Design.cast(_app().activeProduct)
    except Exception:
        return None


def _open_fresh_design() -> adsk.fusion.Design:
    app = _app()
    app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = _active_design()
    if not design:
        raise RuntimeError("Could not create a new Fusion design document.")
    return design


def _has_probe_metadata_parameter(design: Optional[adsk.fusion.Design]) -> bool:
    if not design:
        return False
    try:
        return bool(design.userParameters.itemByName(PROBE_METADATA_PARAM))
    except Exception:
        return False


def _get_design() -> Tuple[adsk.fusion.Design, bool, str]:
    """Return active design whenever possible.

    Earlier probe versions always opened a fresh design, which made repeated
    runs look like "no previous metadata". This script is dev-only, so the
    active document is the intended target. A fresh design is created only when
    Fusion has no active Design product.
    """
    design = _active_design()
    if design:
        if _has_probe_metadata_parameter(design):
            return design, False, "active_design_existing_probe"
        return design, False, "active_design_no_existing_probe"
    return _open_fresh_design(), True, "created_fresh_no_active_design"


def _value_input(expression: str) -> adsk.core.ValueInput:
    return adsk.core.ValueInput.createByString(expression)


def _find_user_parameter(design: adsk.fusion.Design, name: str) -> Optional[adsk.fusion.UserParameter]:
    try:
        return design.userParameters.itemByName(name)
    except Exception:
        return None


def _ensure_user_parameter(
    design: adsk.fusion.Design,
    name: str,
    expression: str,
    unit: str = "",
    comment: str = "",
) -> adsk.fusion.UserParameter:
    existing = _find_user_parameter(design, name)
    if existing:
        return existing
    created = design.userParameters.add(name, _value_input(expression), unit, comment)
    if not created:
        raise RuntimeError(f"Fusion rejected probe parameter {name}.")
    return created


def _entity_token(obj: Any) -> str:
    try:
        return str(obj.entityToken or "")
    except Exception:
        return ""


def _document_info() -> Dict[str, str]:
    app = _app()
    doc = app.activeDocument
    return {
        "name": str(getattr(doc, "name", "") or ""),
        "dataFileId": str(getattr(getattr(doc, "dataFile", None), "id", "") or ""),
        "dataFileName": str(getattr(getattr(doc, "dataFile", None), "name", "") or ""),
    }


def _active_document() -> Optional[adsk.core.Document]:
    try:
        return _app().activeDocument
    except Exception:
        return None


def _document_has_cloud_identity() -> bool:
    info = _document_info()
    return bool(str(info.get("dataFileId") or "").strip())


def _save_active_document(description: str) -> Tuple[bool, str]:
    doc = _active_document()
    if not doc:
        return False, "no_active_document"
    if not _document_has_cloud_identity():
        return False, "document_has_no_dataFileId_save_blank_file_manually_before_running_save_probe"
    try:
        result = doc.save(description)
    except Exception as exc:
        return False, f"save_exception: {exc}"
    if result is False:
        return False, "save_returned_false"
    return True, ""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_compact(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _read_probe_payload(parameter: adsk.fusion.UserParameter) -> Tuple[Optional[Dict[str, Any]], str]:
    raw = str(getattr(parameter, "comment", "") or "")
    if not raw.strip():
        return None, raw
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None, raw
    except Exception:
        return None, raw


def _current_token_snapshot(design: adsk.fusion.Design) -> Dict[str, Dict[str, str]]:
    names = [PROBE_METADATA_PARAM] + list(PROBE_USER_PARAMS) + [DURABLE_SINGLE_PARAM]
    snapshot: Dict[str, Dict[str, str]] = {}
    for name in names:
        param = _find_user_parameter(design, name)
        snapshot[name] = {
            "exists": "true" if param else "false",
            "entityToken": _entity_token(param) if param else "",
            "expression": str(getattr(param, "expression", "") or "") if param else "",
            "unit": str(getattr(param, "unit", "") or "") if param else "",
            "commentLength": str(len(str(getattr(param, "comment", "") or ""))) if param else "0",
        }
    return snapshot


def _sim_param_name(index: int) -> str:
    return f"{SIM_PARAM_PREFIX}{index:04d}"


def _ensure_simulated_parameters(design: adsk.fusion.Design, count: int) -> Tuple[int, List[str]]:
    created = 0
    failures: List[str] = []
    for index in range(1, count + 1):
        name = _sim_param_name(index)
        if _find_user_parameter(design, name):
            continue
        try:
            expression = f"{index} mm"
            comment = f"BP probe simulated real parameter {index}"
            _ensure_user_parameter(design, name, expression, "mm", comment)
            created += 1
            if created % 100 == 0:
                _log(f"Created {created} simulated parameters this run; target {count}.")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            break
    return created, failures


def _collect_simulated_parameter_metadata(design: adsk.fusion.Design, count: int) -> Tuple[Dict[str, Any], List[str]]:
    entries: Dict[str, Any] = {}
    missing: List[str] = []
    for index in range(1, count + 1):
        name = _sim_param_name(index)
        param = _find_user_parameter(design, name)
        if not param:
            missing.append(name)
            continue
        token = _entity_token(param)
        if not token:
            missing.append(f"{name}: missing token")
            continue
        group = SIM_GROUPS[(index - 1) % len(SIM_GROUPS)]
        # Compact current-candidate structure: one doc-level revision/clock,
        # per-parameter stable token, group assignment, and order.
        entries[token] = {
            "g": group,
            "o": index - 1,
        }
    return entries, missing


def _compare_previous_tokens(previous_payload: Optional[Dict[str, Any]], current: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    previous_tokens = {}
    if isinstance(previous_payload, dict):
        previous_tokens = previous_payload.get("probeTokens") if isinstance(previous_payload.get("probeTokens"), dict) else {}
    rows: List[Dict[str, Any]] = []
    stable_count = 0
    changed_count = 0
    missing_previous_count = 0
    for name, current_row in current.items():
        previous_row = previous_tokens.get(name) if isinstance(previous_tokens.get(name), dict) else {}
        previous_token = str(previous_row.get("entityToken") or "")
        current_token = str(current_row.get("entityToken") or "")
        if not previous_token:
            status = "no_previous_token"
            missing_previous_count += 1
        elif previous_token == current_token:
            status = "stable"
            stable_count += 1
        else:
            status = "changed"
            changed_count += 1
        rows.append(
            {
                "name": name,
                "status": status,
                "previousTokenPrefix": previous_token[:48],
                "currentTokenPrefix": current_token[:48],
                "previousTokenLength": len(previous_token),
                "currentTokenLength": len(current_token),
            }
        )
    return {
        "stableCount": stable_count,
        "changedCount": changed_count,
        "missingPreviousCount": missing_previous_count,
        "rows": rows,
    }


def _set_comment_exact(parameter: adsk.fusion.UserParameter, text: str) -> Tuple[bool, str]:
    try:
        parameter.comment = text
    except Exception as exc:
        return False, f"write_failed: {exc}"
    try:
        observed = str(parameter.comment or "")
    except Exception as exc:
        return False, f"readback_failed: {exc}"
    if observed != text:
        return False, f"mismatch: wrote {len(text)} chars, read {len(observed)} chars"
    return True, ""


def _payload_for_target_size(target_size: int) -> str:
    base_payload = {
        "schema": 1,
        "kind": "bp_metadata_probe_size_test",
        "rev": 1,
        "changedAt": 1,
        "writerId": "probe",
        "groups": {
            "token-a": "Dimensions",
            "token-b": "Manufacturing",
        },
        "order": ["token-a", "token-b"],
        "groupUi": {
            "order": ["u:dimensions", "u:manufacturing"],
            "collapsed": {"u:dimensions": False, "u:manufacturing": True},
        },
        "pad": "",
    }
    text = _json_compact(base_payload)
    pad_len = max(0, target_size - len(text) - 16)
    base_payload["pad"] = "x" * pad_len
    return _json_compact(base_payload)


def _durable_param_name(label: str) -> str:
    return DURABLE_SINGLE_PARAM


def _build_durable_payload(
    design: adsk.fusion.Design,
    label: str,
    target_size: int,
    simulated_count: int,
    run_id: str,
    previous_rev: int,
) -> Tuple[str, Dict[str, Any]]:
    entries, missing = _collect_simulated_parameter_metadata(design, simulated_count)
    payload = {
        "schema": 1,
        "kind": "bp_metadata_probe_realistic_metadata",
        "label": label,
        "targetSize": target_size,
        "simulatedParameterCount": simulated_count,
        "rev": previous_rev + 1,
        "runId": run_id,
        "changedAt": int(datetime.now().timestamp() * 1000),
        "groups": list(SIM_GROUPS),
        "groupUi": {
            "order": [f"u:{group.lower()}" for group in SIM_GROUPS],
            "collapsed": {},
        },
        "params": entries,
    }
    text = _json_compact(payload)
    details = {
        "missingCount": len(missing),
        "missing": missing[:20],
        "entryCount": len(entries),
        "actualChars": len(text),
        "targetBytesApprox": target_size,
    }
    return text, details


def _read_durable_payload(parameter: Optional[adsk.fusion.UserParameter]) -> Tuple[Optional[Dict[str, Any]], str, str]:
    if not parameter:
        return None, "", "missing_parameter"
    raw = str(getattr(parameter, "comment", "") or "")
    if not raw:
        return None, raw, "empty_comment"
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return None, raw, f"json_parse_failed: {exc}"
    if not isinstance(payload, dict):
        return None, raw, "json_not_object"
    return payload, raw, ""


def _small_failure_marker(label: str, target_size: int, save_detail: str) -> str:
    return _json_compact(
        {
            "schema": 1,
            "kind": "bp_metadata_probe_durable_size_removed_after_save_failure",
            "label": label,
            "targetSize": target_size,
            "changedAt": int(datetime.now().timestamp() * 1000),
            "saveFailure": save_detail[:500],
        }
    )


def _probe_durable_size_comments(design: adsk.fusion.Design, previous_index: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    stop_after_failure = False
    can_checkpoint_save = _document_has_cloud_identity()
    previous_sizes = {}
    if isinstance(previous_index, dict):
        previous_sizes = previous_index.get("durableSizeComments") if isinstance(previous_index.get("durableSizeComments"), dict) else {}
    verify_only = False
    param = _ensure_user_parameter(design, DURABLE_SINGLE_PARAM, "0", "", "BP metadata probe reusable durable payload")

    for label, target_size, simulated_count in DURABLE_COMMENT_SIZE_TARGETS:
        name = _durable_param_name(label)
        if verify_only:
            param = _find_user_parameter(design, name)
            previous_payload, previous_raw, previous_error = _read_durable_payload(param)
            previous_record = previous_sizes.get(name) if isinstance(previous_sizes.get(name), dict) else {}
            expected_hash = str(previous_record.get("sha256") or "")
            try:
                expected_length = int(previous_record.get("chars") or 0)
            except Exception:
                expected_length = 0
            current_hash = _hash_text(previous_raw) if previous_raw else ""
            verified = bool(param) and bool(previous_raw) and bool(expected_hash) and current_hash == expected_hash and len(previous_raw) == expected_length
            rows.append(
                {
                    "label": label,
                    "parameterName": name,
                    "targetBytesApprox": target_size,
                    "simulatedParameterCount": simulated_count,
                    "mode": "verify_only",
                    "writeOk": False,
                    "writeDetail": "verify_only_existing_index",
                    "chars": len(previous_raw),
                    "sha256": current_hash,
                    "previousHadJson": isinstance(previous_payload, dict),
                    "previousError": previous_error,
                    "previousChars": len(previous_raw),
                    "previousExpectedChars": expected_length,
                    "previousHashMatchedIndex": verified,
                    "entityToken": _entity_token(param) if param else "",
                    "checkpointSaveAttempted": False,
                    "checkpointSaveOk": False,
                    "checkpointSaveDetail": "verify_only_existing_index",
                    "recoverySaveAttempted": False,
                    "recoverySaveOk": False,
                    "recoverySaveDetail": "",
                    "exists": bool(param),
                    "actualPayloadChars": len(previous_raw),
                    "entryCount": int(previous_payload.get("simulatedParameterCount") or 0) if isinstance(previous_payload, dict) else 0,
                }
            )
            continue
        if stop_after_failure:
            rows.append(
                {
                    "label": label,
                    "parameterName": name,
                    "targetBytesApprox": target_size,
                    "simulatedParameterCount": simulated_count,
                    "mode": "write",
                    "writeOk": False,
                    "writeDetail": "skipped_after_previous_save_failure",
                    "chars": 0,
                    "sha256": "",
                    "previousHadJson": False,
                    "previousError": "",
                    "previousChars": 0,
                    "previousExpectedChars": 0,
                    "previousHashMatchedIndex": False,
                    "entityToken": "",
                    "checkpointSaveAttempted": False,
                    "checkpointSaveOk": False,
                    "checkpointSaveDetail": "skipped_after_previous_save_failure",
                    "recoverySaveAttempted": False,
                    "recoverySaveOk": False,
                    "recoverySaveDetail": "",
                    "exists": False,
                    "actualPayloadChars": 0,
                    "entryCount": 0,
                }
            )
            continue
        previous_payload, previous_raw, previous_error = _read_durable_payload(param)
        previous_record = previous_sizes.get(label) if isinstance(previous_sizes.get(label), dict) else {}
        previous_hash = str(previous_record.get("sha256") or "")
        previous_length = int(previous_record.get("chars") or 0) if str(previous_record.get("chars") or "").isdigit() else 0
        previous_rev = int(previous_payload.get("rev") or 0) if isinstance(previous_payload, dict) else 0
        previous_verified = bool(previous_raw) and bool(previous_hash) and _hash_text(previous_raw) == previous_hash and len(previous_raw) == previous_length

        created_count, create_failures = _ensure_simulated_parameters(design, simulated_count)
        desired_text, payload_details = _build_durable_payload(
            design,
            label,
            target_size,
            simulated_count,
            run_id,
            previous_rev,
        )
        write_ok, write_detail = _set_comment_exact(param, desired_text)
        observed = str(getattr(param, "comment", "") or "") if write_ok else ""
        checkpoint_attempted = bool(write_ok and can_checkpoint_save)
        checkpoint_ok = False
        checkpoint_detail = "not_attempted_unsaved_document" if write_ok and not can_checkpoint_save else ""
        recovery_attempted = False
        recovery_ok = False
        recovery_detail = ""
        if checkpoint_attempted:
            checkpoint_ok, checkpoint_detail = _save_active_document(f"BP metadata probe checkpoint {label}")
            if not checkpoint_ok:
                stop_after_failure = True
                marker = _small_failure_marker(label, target_size, checkpoint_detail)
                marker_ok, marker_detail = _set_comment_exact(param, marker)
                recovery_attempted = True
                if marker_ok:
                    recovery_ok, recovery_detail = _save_active_document(f"BP metadata probe recovery after {label}")
                else:
                    recovery_ok = False
                    recovery_detail = f"marker_write_failed: {marker_detail}"
        rows.append(
            {
                "label": label,
                "parameterName": name,
                "targetBytesApprox": target_size,
                "simulatedParameterCount": simulated_count,
                "mode": "write",
                "writeOk": bool(write_ok),
                "writeDetail": write_detail or ("; ".join(create_failures[:3]) if create_failures else ""),
                "chars": len(observed) if write_ok else 0,
                "sha256": _hash_text(observed) if write_ok else "",
                "previousHadJson": isinstance(previous_payload, dict),
                "previousError": previous_error,
                "previousChars": len(previous_raw),
                "previousExpectedChars": previous_length,
                "previousHashMatchedIndex": previous_verified,
                "entityToken": _entity_token(param),
                "checkpointSaveAttempted": checkpoint_attempted,
                "checkpointSaveOk": checkpoint_ok,
                "checkpointSaveDetail": checkpoint_detail,
                "recoverySaveAttempted": recovery_attempted,
                "recoverySaveOk": recovery_ok,
                "recoverySaveDetail": recovery_detail,
                "exists": True,
                "createdSimParamsThisStep": created_count,
                "createFailures": create_failures[:10],
                "actualPayloadChars": payload_details.get("actualChars"),
                "entryCount": payload_details.get("entryCount"),
                "missingMetadataCount": payload_details.get("missingCount"),
                "missingMetadata": payload_details.get("missing"),
            }
        )
        if not write_ok:
            _log(f"Durable size write failed for {name}: {write_detail}")
        if checkpoint_attempted and not checkpoint_ok:
            _log(f"Checkpoint save failed after {name}; stopped larger payloads. {checkpoint_detail}")

    ok_count = sum(1 for row in rows if row.get("writeOk"))
    previous_verified_count = sum(1 for row in rows if row.get("previousHashMatchedIndex"))
    checkpoint_ok_count = sum(1 for row in rows if row.get("checkpointSaveOk"))
    checkpoint_failed_count = sum(1 for row in rows if row.get("checkpointSaveAttempted") and not row.get("checkpointSaveOk"))
    return {
        "runId": run_id,
        "mode": "verify_only" if verify_only else "write",
        "checkpointSaveEnabled": can_checkpoint_save,
        "okCount": ok_count,
        "failedCount": len(rows) - ok_count,
        "previousVerifiedCount": previous_verified_count,
        "checkpointSaveOkCount": checkpoint_ok_count,
        "checkpointSaveFailedCount": checkpoint_failed_count,
        "rows": rows,
    }


def _probe_comment_capacity(parameter: adsk.fusion.UserParameter) -> Dict[str, Any]:
    rows = []
    max_exact = 0
    first_failure = None
    for target in COMMENT_SIZE_TARGETS:
        text = _payload_for_target_size(target)
        ok, detail = _set_comment_exact(parameter, text)
        rows.append(
            {
                "targetBytesApprox": target,
                "actualChars": len(text),
                "ok": ok,
                "detail": detail,
                "sha256": _hash_text(text) if ok else "",
            }
        )
        if ok:
            max_exact = len(text)
        elif first_failure is None:
            first_failure = {"targetBytesApprox": target, "actualChars": len(text), "detail": detail}
            break
    return {
        "maxExactCharsInThisRun": max_exact,
        "firstFailure": first_failure,
        "rows": rows,
    }


def _estimate_metadata_capacity(max_chars: int, current_param_count: int) -> Dict[str, Any]:
    example_entry = _json_compact(
        {
            "token-example-abcdefghijklmnopqrstuvwxyz": {
                "g": "Example Group Name",
                "r": 12345,
                "t": 1780170000000,
            }
        }
    )
    approx_entry_chars = max(1, len(example_entry) - 2)
    reserved_chars = 600
    estimated_entries = max(0, (max_chars - reserved_chars) // approx_entry_chars) if max_chars > reserved_chars else 0
    return {
        "currentUserParameterCount": current_param_count,
        "approxCharsPerGroupEntry": approx_entry_chars,
        "estimatedEntriesAtMaxExactChars": estimated_entries,
        "fitsCurrentCountByEstimate": estimated_entries >= current_param_count,
    }


def _write_report(report: Dict[str, Any]) -> Tuple[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = Path(tempfile.gettempdir()) / "bp_metadata_parameter_probe"
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"probe_{timestamp}.json"
    txt_path = root / f"probe_{timestamp}.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    txt_path.write_text(_format_text_report(report), encoding="utf-8")
    return str(json_path), str(txt_path)


def _format_text_report(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("BP Metadata Parameter Probe")
    lines.append(f"timestamp: {report.get('timestamp')}")
    lines.append(f"platform: {report.get('platform')}")
    lines.append(f"createdFreshDesign: {report.get('createdFreshDesign')}")
    lines.append(f"designSelectionReason: {report.get('designSelectionReason')}")
    lines.append(f"document: {json.dumps(report.get('document'), ensure_ascii=True)}")
    lines.append("")
    lines.append("Comment capacity:")
    capacity = report.get("commentCapacity") or {}
    lines.append(f"- max exact chars: {capacity.get('maxExactCharsInThisRun')}")
    lines.append(f"- first failure: {capacity.get('firstFailure')}")
    for row in capacity.get("rows") or []:
        lines.append(f"  - target {row.get('targetBytesApprox')}: ok={row.get('ok')} chars={row.get('actualChars')} {row.get('detail') or ''}")
    lines.append("")
    lines.append("Token comparison:")
    comparison = report.get("tokenComparison") or {}
    lines.append(f"- stable: {comparison.get('stableCount')}")
    lines.append(f"- changed: {comparison.get('changedCount')}")
    lines.append(f"- no previous: {comparison.get('missingPreviousCount')}")
    for row in comparison.get("rows") or []:
        lines.append(
            f"  - {row.get('name')}: {row.get('status')} prevLen={row.get('previousTokenLength')} currLen={row.get('currentTokenLength')}"
        )
    lines.append("")
    lines.append("Capacity estimate:")
    lines.append(json.dumps(report.get("capacityEstimate") or {}, indent=2, ensure_ascii=True))
    lines.append("")
    lines.append("Durable size comments:")
    durable = report.get("durableSizeComments") or {}
    lines.append(f"- mode: {durable.get('mode')}")
    lines.append(f"- checkpoint save enabled: {durable.get('checkpointSaveEnabled')}")
    lines.append(f"- writes ok/failed: {durable.get('okCount')}/{durable.get('failedCount')}")
    lines.append(f"- previous verified: {durable.get('previousVerifiedCount')}")
    lines.append(f"- checkpoint saves ok/failed: {durable.get('checkpointSaveOkCount')}/{durable.get('checkpointSaveFailedCount')}")
    for row in durable.get("rows") or []:
        lines.append(
            f"  - {row.get('label')}: mode={row.get('mode')} exists={row.get('exists')} "
            f"simParams={row.get('simulatedParameterCount')} entries={row.get('entryCount')} "
            f"target={row.get('targetBytesApprox')} actualChars={row.get('actualPayloadChars')} "
            f"writeOk={row.get('writeOk')} chars={row.get('chars')} "
            f"prevVerified={row.get('previousHashMatchedIndex')} "
            f"saveOk={row.get('checkpointSaveOk')} "
            f"recoveryOk={row.get('recoverySaveOk')} "
            f"{row.get('writeDetail') or row.get('checkpointSaveDetail') or row.get('previousError') or ''}"
        )
    lines.append("")
    lines.append("Manual undo probe:")
    lines.append("- Script leaves one final comment write on _bp_probe_metadata_v1.")
    lines.append("- Open Fusion undo dropdown/history and count entries created by this run.")
    lines.append("- Desired future BP behavior: one metadata write should become one undo entry or one grouped command transaction.")
    lines.append("")
    lines.append("Save/reopen durability:")
    lines.append("- Save this test design, close it, reopen it, rerun this script.")
    lines.append("- Token comparison should show stable for probe params if entityToken is durable enough for this storage design.")
    return "\n".join(lines) + "\n"


def _run_probe() -> Dict[str, Any]:
    design, created_fresh, design_selection_reason = _get_design()
    _ensure_user_parameter(design, PROBE_USER_PARAMS[0], "10 mm", "mm", "BP metadata probe user parameter A")
    _ensure_user_parameter(design, PROBE_USER_PARAMS[1], f"{PROBE_USER_PARAMS[0]} * 2", "mm", "BP metadata probe user parameter B")
    metadata_param = _ensure_user_parameter(design, PROBE_METADATA_PARAM, "0", "", "")

    previous_payload, previous_raw = _read_probe_payload(metadata_param)
    durable_size_comments = _probe_durable_size_comments(design, previous_payload)
    token_snapshot_before = _current_token_snapshot(design)
    token_comparison = _compare_previous_tokens(previous_payload, token_snapshot_before)
    comment_capacity = _probe_comment_capacity(metadata_param)

    try:
        user_param_count = int(design.userParameters.count)
    except Exception:
        user_param_count = 0
    capacity_estimate = _estimate_metadata_capacity(
        int(comment_capacity.get("maxExactCharsInThisRun") or 0),
        user_param_count,
    )

    if durable_size_comments.get("mode") == "verify_only" and isinstance(previous_payload, dict):
        durable_index_payload = previous_payload.get("durableSizeComments") if isinstance(previous_payload.get("durableSizeComments"), dict) else {}
    else:
        durable_index_payload = {
            row["label"]: {
                "label": row["label"],
                "parameterName": row["parameterName"],
                "targetBytesApprox": row["targetBytesApprox"],
                "chars": row["chars"],
                "sha256": row["sha256"],
                "writeOk": row["writeOk"],
                "checkpointSaveOk": row.get("checkpointSaveOk", False),
                "simulatedParameterCount": row.get("simulatedParameterCount", 0),
                "actualPayloadChars": row.get("actualPayloadChars", row.get("chars", 0)),
                "entryCount": row.get("entryCount", 0),
            }
            for row in durable_size_comments.get("rows") or []
            if row.get("writeOk") and (
                not durable_size_comments.get("checkpointSaveEnabled")
                or row.get("checkpointSaveOk")
            )
        }

    final_payload = {
        "schema": 1,
        "kind": "bp_metadata_parameter_probe",
        "rev": int((previous_payload or {}).get("rev") or 0) + 1 if isinstance(previous_payload, dict) else 1,
        "changedAt": int(datetime.now().timestamp() * 1000),
        "writerId": f"{platform.node()}:{os.getpid()}",
        "document": _document_info(),
        "probeTokens": token_snapshot_before,
        "previousPayloadWasJson": isinstance(previous_payload, dict),
        "previousRawCommentLength": len(previous_raw),
        "durableSizeComments": durable_index_payload,
        "commentCapacity": comment_capacity,
        "tokenComparison": token_comparison,
        "capacityEstimate": capacity_estimate,
    }
    final_text = _json_compact(final_payload)
    final_payload["contentHash"] = _hash_text(final_text)
    final_text = _json_compact(final_payload)
    final_write_ok, final_write_detail = _set_comment_exact(metadata_param, final_text)
    final_save_attempted = bool(final_write_ok and _document_has_cloud_identity())
    final_save_ok = False
    final_save_detail = "not_attempted_unsaved_document" if final_write_ok and not _document_has_cloud_identity() else ""
    if final_save_attempted:
        final_save_ok, final_save_detail = _save_active_document("BP metadata probe final index")

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
        "platform": platform.platform(),
        "createdFreshDesign": created_fresh,
        "designSelectionReason": design_selection_reason,
        "document": _document_info(),
        "metadataParameter": PROBE_METADATA_PARAM,
        "probeUserParameters": list(PROBE_USER_PARAMS),
        "previousPayloadWasJson": isinstance(previous_payload, dict),
        "previousRawCommentLength": len(previous_raw),
        "tokenSnapshotBeforeFinalWrite": token_snapshot_before,
        "tokenComparison": token_comparison,
        "commentCapacity": comment_capacity,
        "durableSizeComments": durable_size_comments,
        "capacityEstimate": capacity_estimate,
        "finalWrite": {
            "ok": final_write_ok,
            "detail": final_write_detail,
            "chars": len(final_text),
            "sha256": _hash_text(final_text),
            "saveAttempted": final_save_attempted,
            "saveOk": final_save_ok,
            "saveDetail": final_save_detail,
        },
        "manualChecks": [
            "Inspect Fusion undo dropdown/history and count undo entries from this run.",
            "Save, close, reopen, then rerun to test entityToken/comment durability.",
            "Inspect Parameters dialog: probe metadata parameter should be visible and user-editable.",
        ],
    }
    return report


def run(_context: Any) -> None:
    try:
        report = _run_probe()
        json_path, txt_path = _write_report(report)
        summary = (
            "Probe complete.\n\n"
            f"Text report:\n{txt_path}\n\n"
            f"JSON report:\n{json_path}\n\n"
            f"Design selection: {report.get('designSelectionReason')}\n"
            f"Max exact comment chars this run: {report['commentCapacity']['maxExactCharsInThisRun']}\n"
            f"Token stable/changed/no previous: "
            f"{report['tokenComparison']['stableCount']}/"
            f"{report['tokenComparison']['changedCount']}/"
            f"{report['tokenComparison']['missingPreviousCount']}\n"
            f"Durable size writes ok/failed: "
            f"{report['durableSizeComments']['okCount']}/"
            f"{report['durableSizeComments']['failedCount']}\n"
            f"Durable mode: {report['durableSizeComments']['mode']}\n"
            f"Checkpoint saves ok/failed: "
            f"{report['durableSizeComments']['checkpointSaveOkCount']}/"
            f"{report['durableSizeComments']['checkpointSaveFailedCount']}\n"
            f"Previous durable hashes verified: "
            f"{report['durableSizeComments']['previousVerifiedCount']}\n\n"
            "For durability: save this test design, close/reopen, rerun script."
        )
        _log(summary)
        _message(summary)
    except Exception:
        error = traceback.format_exc()
        _log(error)
        _message(f"Probe failed:\n{error}")


def stop(_context: Any) -> None:
    return None
