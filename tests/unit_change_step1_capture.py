"""
unit_change_step1_capture.py
============================
PURPOSE
  Capture a before-snapshot of all user parameters (entity tokens, units,
  and BetterParameters metadata attributes) and write the snapshot to a
  JSON file in the same directory.

HOW TO RUN
  In Fusion 360: Scripts and Add-Ins → Scripts → Run Script → pick this file.
  A dialog confirms the snapshot was written and shows where it is stored.

WORKFLOW
  1. Run this script BEFORE making any unit change in the native Parameters UI.
  2. Change one or more parameter units in Fusion's native Parameters dialog.
  3. Run unit_change_step2_compare.py — it loads the snapshot and reports
     what changed (token identity, attribute survival, etc.).
"""

import json
import os
import datetime

import adsk.core
import adsk.fusion


SNAPSHOT_FILENAME = "unit_change_snapshot.json"
BP_NAMESPACE = "BetterParameters"
BP_ATTR_NAMES = ["group", "metadataChangedAt", "metadataRevision",
                 "metadataWriterId", "metadataWriterVersion"]


def _read_bp_attributes(param):
    """Return a dict of BetterParameters attribute name → value (or None)."""
    result = {}
    for attr_name in BP_ATTR_NAMES:
        attr = param.attributes.itemByName(BP_NAMESPACE, attr_name)
        result[attr_name] = attr.value if attr else None
    return result


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("No active Fusion design found. Open a document first.")
        return

    snapshot = {
        "capturedAt": datetime.datetime.now().isoformat(),
        "documentId": app.activeDocument.dataFile.id if app.activeDocument.dataFile else "",
        "documentName": app.activeDocument.name,
        "parameters": [],
    }

    params = design.userParameters
    for i in range(params.count):
        param = params.item(i)
        if not param:
            continue
        snapshot["parameters"].append({
            "name": param.name,
            "unit": param.unit,
            "expression": param.expression,
            "entityToken": param.entityToken,
            "isDeletable": param.isDeletable,
            "isFavorite": param.isFavorite,
            "comment": param.comment or "",
            "betterParametersAttributes": _read_bp_attributes(param),
        })

    snapshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SNAPSHOT_FILENAME)
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    count = len(snapshot["parameters"])
    ui.messageBox(
        f"Snapshot captured: {count} user parameter(s).\n\n"
        f"Saved to:\n{snapshot_path}\n\n"
        f"Now change a parameter unit in Fusion's native Parameters dialog,\n"
        f"then run unit_change_step2_compare.py."
    )
