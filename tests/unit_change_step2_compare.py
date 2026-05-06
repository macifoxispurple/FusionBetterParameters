"""
unit_change_step2_compare.py
============================
PURPOSE
  Load the snapshot written by unit_change_step1_capture.py and compare it
  against the current live parameter state to determine exactly what Fusion
  did internally when the unit was changed via the native Parameters UI.

HOW TO RUN
  In Fusion 360: Scripts and Add-Ins → Scripts → Run Script → pick this file.
  Run AFTER changing a unit in Fusion's native Parameters dialog.

WHAT THIS ANSWERS
  1. Entity token identity   — did the token survive? (In-place) or change? (Delete+recreate)
  2. Attribute survival      — did BetterParameters metadata attributes survive?
  3. Name/expression/unit    — did any other properties change unexpectedly?

INTERPRETATION
  Token unchanged + attributes present  →  Fusion mutated the parameter in-place.
                                            Our delete+recreate approach is unnecessary
                                            (and harmful — we lose the token).
  Token changed   + attributes gone     →  Fusion also does delete+recreate internally.
                                            Our implementation matches native behavior.
  Token unchanged + attributes gone     →  Unusual. In-place mutation somehow cleared attrs.
                                            Worth investigating further.
"""

import json
import os

import adsk.core
import adsk.fusion


SNAPSHOT_FILENAME = "unit_change_snapshot.json"
BP_NAMESPACE = "BetterParameters"
BP_ATTR_NAMES = ["group", "metadataChangedAt", "metadataRevision",
                 "metadataWriterId", "metadataWriterVersion"]


def _read_bp_attributes(param):
    result = {}
    for attr_name in BP_ATTR_NAMES:
        attr = param.attributes.itemByName(BP_NAMESPACE, attr_name)
        result[attr_name] = attr.value if attr else None
    return result


def _attrs_survived(before_attrs, after_attrs):
    """True if at least one non-None attribute from before is still present after."""
    for k, v in before_attrs.items():
        if v is not None and after_attrs.get(k) == v:
            return True
    return False


def _any_attrs_set(attrs):
    return any(v is not None for v in attrs.values())


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    snapshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SNAPSHOT_FILENAME)
    if not os.path.exists(snapshot_path):
        ui.messageBox(
            f"Snapshot file not found:\n{snapshot_path}\n\n"
            "Run unit_change_step1_capture.py first."
        )
        return

    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("No active Fusion design found. Open a document first.")
        return

    # Build lookup maps from live state
    live_by_token = {}
    live_by_name = {}
    params = design.userParameters
    for i in range(params.count):
        param = params.item(i)
        if not param:
            continue
        token = param.entityToken
        entry = {
            "name": param.name,
            "unit": param.unit,
            "expression": param.expression,
            "entityToken": token,
            "isFavorite": param.isFavorite,
            "comment": param.comment or "",
            "betterParametersAttributes": _read_bp_attributes(param),
        }
        live_by_token[token] = entry
        live_by_name[param.name] = entry

    lines = [
        f"Snapshot from: {snapshot.get('capturedAt', 'unknown')}",
        f"Document: {snapshot.get('documentName', 'unknown')}",
        "",
    ]

    interesting = []  # parameters where something changed

    for before in snapshot["parameters"]:
        name = before["name"]
        old_token = before["entityToken"]
        old_unit = before["unit"]
        old_attrs = before.get("betterParametersAttributes", {})
        had_attrs = _any_attrs_set(old_attrs)

        # Try to find the parameter after the change
        by_token = live_by_token.get(old_token)
        by_name = live_by_name.get(name)

        if by_token:
            # Token is still alive — in-place or no change at all
            after = by_token
            token_changed = False
            found_how = "by token (same token)"
        elif by_name:
            # Token gone but name found — delete+recreate or rename-in-place with new token
            after = by_name
            token_changed = True
            found_how = "by name (token changed)"
        else:
            # Completely missing
            interesting.append(
                f"PARAMETER GONE: '{name}' (was unit={old_unit}) — "
                "not found by token or name after unit change."
            )
            continue

        unit_changed = (after["unit"] != old_unit)
        if not unit_changed and not token_changed:
            continue  # No observable change for this parameter — skip

        new_attrs = after.get("betterParametersAttributes", {})
        attrs_ok = _attrs_survived(old_attrs, new_attrs) if had_attrs else None

        block = [f"PARAMETER: '{name}'"]
        block.append(f"  Unit:  {old_unit!r}  →  {after['unit']!r}  {'(changed)' if unit_changed else '(unchanged)'}")
        block.append(f"  Token: {old_token[:24]}...")
        if token_changed:
            block.append(f"    → NEW token: {after['entityToken'][:24]}...  ← TOKEN CHANGED (delete+recreate)")
        else:
            block.append(f"    → Same token  ← IN-PLACE MUTATION")
        if had_attrs:
            if attrs_ok:
                block.append(f"  BP Attributes: SURVIVED")
            else:
                block.append(f"  BP Attributes: GONE  ← attributes were lost")
        else:
            block.append(f"  BP Attributes: (none were set before — cannot test survival)")
        block.append(f"  Found: {found_how}")

        interesting.append("\n".join(block))

    if not interesting:
        lines.append("No observable changes detected. Either no unit was changed,")
        lines.append("or the changed parameter is not in the snapshot.")
    else:
        lines.extend(interesting)

    lines.append("")
    lines.append("--- VERDICT ---")

    # Derive overall verdict
    token_changes = [b for b in interesting if "TOKEN CHANGED" in b]
    in_place = [b for b in interesting if "IN-PLACE" in b]
    if token_changes and not in_place:
        lines.append("DELETE+RECREATE confirmed: tokens changed on unit-changed parameters.")
        lines.append("Our BE implementation (delete+recreate) matches native Fusion behavior.")
    elif in_place and not token_changes:
        lines.append("IN-PLACE MUTATION confirmed: tokens survived.")
        lines.append("Native Fusion has a mutation path our Python API does not expose.")
        lines.append("Our BE delete+recreate is NOT equivalent to native behavior.")
    elif token_changes and in_place:
        lines.append("MIXED results — some parameters changed tokens, some did not.")
        lines.append("Investigate individual entries above.")
    else:
        lines.append("No unit-changed parameters detected in comparison.")

    ui.messageBox("\n".join(lines))
