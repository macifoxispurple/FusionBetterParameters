"""
unit_change_force_attempt.py
============================
PURPOSE
  Systematically attempt every plausible Python API path to change a
  UserParameter's unit in-place, and record the full outcome of each
  attempt to a text log file for inspection.

  This is a research script — it does NOT represent a usable technique.
  The goal is to understand exactly where and why the API boundary exists.

HOW TO RUN
  In Fusion 360: Scripts and Add-Ins → Scripts → Run Script → pick this file.
  Results are written to:
    <this directory>/unit_change_force_results.txt

WHAT IS TESTED
  A temporary parameter "_bp_unit_test" (mm) is created fresh for each
  attempt. After each attempt the parameter's unit, token, and expression
  are recorded. The parameter is deleted between attempts where possible
  so each attempt starts clean.

  Attempts:
    1.  Direct property assignment         param.unit = "ft"
    2.  Expression with embedded unit      param.expression = "5 ft"
    3.  Value assignment (numeric)         param.value = 0.1524  (= 6 in)
    4.  ValueInput via createByString      re-add via userParameters.add
    5.  allParameters reference variant   look up via allParameters, try assign
    6.  Attribute inspection              dir(), type(), MRO, property descriptors
    7.  Unit property descriptor probe    type(param).__dict__.get("unit")
    8.  expression → unit coercion check  set expression to "6 in", read unit back
    9.  textValue assignment probe        param.textValue = "6 in"
   10.  comment roundtrip (control)       param.comment = "test"  (known to work)
"""

import datetime
import os
import traceback

import adsk.core
import adsk.fusion


OUTPUT_FILENAME = "unit_change_force_results.txt"
TEST_PARAM_NAME = "_bp_unit_test"
TEST_UNIT_START = "mm"
TEST_UNIT_TARGET = "ft"
TEST_EXPRESSION_START = "100 mm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshot(param):
    """Return a dict of observable parameter state."""
    try:
        return {
            "unit": param.unit,
            "expression": param.expression,
            "token": param.entityToken,
            "comment": param.comment,
            "isValid": param.isValid,
        }
    except Exception as exc:
        return {"snapshot_error": str(exc)}


def _tokens_match(before, after):
    return before.get("token") == after.get("token")


def _unit_changed(before, after):
    return before.get("unit") != after.get("unit")


def _create_test_param(design):
    """Create (or recreate) the test parameter. Returns param or None."""
    existing = design.userParameters.itemByName(TEST_PARAM_NAME)
    if existing:
        try:
            existing.deleteMe()
        except Exception:
            pass
    vi = adsk.core.ValueInput.createByString(TEST_EXPRESSION_START)
    param = design.userParameters.add(TEST_PARAM_NAME, vi, TEST_UNIT_START, "unit_force_test")
    return param


def _delete_test_param(design):
    existing = design.userParameters.itemByName(TEST_PARAM_NAME)
    if existing:
        try:
            existing.deleteMe()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Individual attempt functions — each returns a result dict
# ---------------------------------------------------------------------------

def attempt_direct_assignment(design, log):
    log("=" * 60)
    log("ATTEMPT 1: Direct property assignment  param.unit = 'ft'")
    log("=" * 60)
    param = _create_test_param(design)
    before = _snapshot(param)
    log(f"  Before: unit={before['unit']!r}  token={before['token'][:32]}...")

    exception_text = None
    try:
        param.unit = TEST_UNIT_TARGET
        log("  Assignment did not raise an exception.")
    except AttributeError as exc:
        exception_text = f"AttributeError: {exc}"
        log(f"  AttributeError raised: {exc}")
    except RuntimeError as exc:
        exception_text = f"RuntimeError: {exc}"
        log(f"  RuntimeError raised: {exc}")
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"
        log(f"  Exception raised: {type(exc).__name__}: {exc}")

    # Re-fetch from collection — avoid using a potentially stale ref
    param2 = design.userParameters.itemByName(TEST_PARAM_NAME)
    after = _snapshot(param2) if param2 else {"unit": "PARAM GONE", "token": "", "expression": ""}
    log(f"  After:  unit={after.get('unit')!r}  token={after.get('token', '')[:32]}...")
    log(f"  Unit changed:  {_unit_changed(before, after)}")
    log(f"  Token stable:  {_tokens_match(before, after)}")
    log(f"  Exception:     {exception_text or 'None'}")
    _delete_test_param(design)
    return {"attempt": 1, "unit_changed": _unit_changed(before, after),
            "token_stable": _tokens_match(before, after), "exception": exception_text}


def attempt_expression_with_unit(design, log):
    log("")
    log("=" * 60)
    log("ATTEMPT 2: Set expression with target unit embedded")
    log("           param.expression = '5 ft'")
    log("=" * 60)
    param = _create_test_param(design)
    before = _snapshot(param)
    log(f"  Before: unit={before['unit']!r}  expression={before['expression']!r}")

    exception_text = None
    try:
        param.expression = "5 ft"
        log("  Assignment did not raise.")
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"
        log(f"  Exception: {exception_text}")

    param2 = design.userParameters.itemByName(TEST_PARAM_NAME)
    after = _snapshot(param2) if param2 else {"unit": "PARAM GONE", "expression": "", "token": ""}
    log(f"  After:  unit={after.get('unit')!r}  expression={after.get('expression')!r}")
    log(f"  Unit changed:  {_unit_changed(before, after)}")
    log(f"  Token stable:  {_tokens_match(before, after)}")
    log(f"  Exception:     {exception_text or 'None'}")
    _delete_test_param(design)
    return {"attempt": 2, "unit_changed": _unit_changed(before, after),
            "token_stable": _tokens_match(before, after), "exception": exception_text}


def attempt_value_assignment(design, log):
    log("")
    log("=" * 60)
    log("ATTEMPT 3: Numeric value assignment in target unit's magnitude")
    log("           param.value = 0.3048  (1 ft in internal units = cm)")
    log("           Note: Fusion stores values in cm internally.")
    log("=" * 60)
    param = _create_test_param(design)
    before = _snapshot(param)
    log(f"  Before: unit={before['unit']!r}  expression={before['expression']!r}")

    exception_text = None
    try:
        # 1 ft = 30.48 cm. Fusion internal unit for length is cm.
        param.value = 30.48
        log("  Assignment did not raise.")
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"
        log(f"  Exception: {exception_text}")

    param2 = design.userParameters.itemByName(TEST_PARAM_NAME)
    after = _snapshot(param2) if param2 else {"unit": "PARAM GONE", "expression": "", "token": ""}
    log(f"  After:  unit={after.get('unit')!r}  expression={after.get('expression')!r}")
    log(f"  Unit changed:  {_unit_changed(before, after)}")
    log(f"  Token stable:  {_tokens_match(before, after)}")
    log(f"  Exception:     {exception_text or 'None'}")
    _delete_test_param(design)
    return {"attempt": 3, "unit_changed": _unit_changed(before, after),
            "token_stable": _tokens_match(before, after), "exception": exception_text}


def attempt_all_parameters_ref(design, log):
    log("")
    log("=" * 60)
    log("ATTEMPT 4: Access via design.allParameters (different collection)")
    log("           Does a different reference type expose a setter?")
    log("=" * 60)
    _create_test_param(design)
    param_via_all = design.allParameters.itemByName(TEST_PARAM_NAME)
    if not param_via_all:
        log("  Parameter not found via allParameters. Skipping.")
        _delete_test_param(design)
        return {"attempt": 4, "skipped": True}

    log(f"  Type via allParameters: {type(param_via_all).__name__}")
    log(f"  Type via userParameters: {type(design.userParameters.itemByName(TEST_PARAM_NAME)).__name__}")
    before = _snapshot(param_via_all)
    log(f"  Before: unit={before['unit']!r}")

    exception_text = None
    try:
        param_via_all.unit = TEST_UNIT_TARGET
        log("  Assignment did not raise.")
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"
        log(f"  Exception: {exception_text}")

    param2 = design.userParameters.itemByName(TEST_PARAM_NAME)
    after = _snapshot(param2) if param2 else {"unit": "PARAM GONE", "token": "", "expression": ""}
    log(f"  After:  unit={after.get('unit')!r}")
    log(f"  Unit changed:  {_unit_changed(before, after)}")
    log(f"  Token stable:  {_tokens_match(before, after)}")
    log(f"  Exception:     {exception_text or 'None'}")
    _delete_test_param(design)
    return {"attempt": 4, "unit_changed": _unit_changed(before, after),
            "token_stable": _tokens_match(before, after), "exception": exception_text}


def attempt_object_inspection(design, log):
    log("")
    log("=" * 60)
    log("ATTEMPT 5: Object inspection — dir(), type(), MRO, property descriptors")
    log("           Looking for any hidden setter or mutation method.")
    log("=" * 60)
    param = _create_test_param(design)

    log(f"  type(param):            {type(param)}")
    log(f"  type(param).__name__:   {type(param).__name__}")

    try:
        mro = [c.__name__ for c in type(param).__mro__]
        log(f"  MRO: {' -> '.join(mro)}")
    except Exception as exc:
        log(f"  MRO error: {exc}")

    try:
        all_attrs = dir(param)
        log(f"  dir() count: {len(all_attrs)}")
        # Filter to plausibly unit-related names
        unit_related = [a for a in all_attrs if "unit" in a.lower()]
        log(f"  Unit-related attrs: {unit_related}")
        # Also log any 'set' methods
        setters = [a for a in all_attrs if a.lower().startswith("set")]
        log(f"  Methods starting with 'set': {setters}")
        # Full dir dump for record
        log(f"  Full dir(): {all_attrs}")
    except Exception as exc:
        log(f"  dir() error: {exc}")

    try:
        cls = type(param)
        unit_descriptor = cls.__dict__.get("unit")
        log(f"  type(param).__dict__['unit']:  {unit_descriptor}")
        if unit_descriptor is not None:
            log(f"    fget: {getattr(unit_descriptor, 'fget', 'N/A')}")
            log(f"    fset: {getattr(unit_descriptor, 'fset', 'N/A')}")
    except Exception as exc:
        log(f"  Descriptor probe error: {exc}")

    _delete_test_param(design)
    return {"attempt": 5, "informational": True}


def attempt_expression_coercion_read(design, log):
    log("")
    log("=" * 60)
    log("ATTEMPT 6: Expression coercion — set expression to '6 in', read unit back")
    log("           Does Fusion update the unit field to match expression unit?")
    log("=" * 60)
    param = _create_test_param(design)
    before = _snapshot(param)
    log(f"  Before: unit={before['unit']!r}  expression={before['expression']!r}")

    exception_text = None
    try:
        param.expression = "6 in"
        log("  param.expression = '6 in' did not raise.")
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"
        log(f"  Exception setting expression: {exception_text}")

    param2 = design.userParameters.itemByName(TEST_PARAM_NAME)
    after = _snapshot(param2) if param2 else {"unit": "PARAM GONE", "expression": "", "token": ""}
    log(f"  After:  unit={after.get('unit')!r}  expression={after.get('expression')!r}")
    log(f"  Unit changed:  {_unit_changed(before, after)}")
    log(f"  Token stable:  {_tokens_match(before, after)}")
    log(f"  Note: expression may accept cross-unit literal but unit field may not follow.")
    log(f"  Exception:     {exception_text or 'None'}")
    _delete_test_param(design)
    return {"attempt": 6, "unit_changed": _unit_changed(before, after),
            "token_stable": _tokens_match(before, after), "exception": exception_text}


def attempt_text_value_assignment(design, log):
    log("")
    log("=" * 60)
    log("ATTEMPT 7: textValue assignment probe")
    log("           param.textValue = '6 in'  (textValue is for Text params)")
    log("           Testing whether this path exists and what it does.")
    log("=" * 60)
    param = _create_test_param(design)
    before = _snapshot(param)
    log(f"  Before: unit={before['unit']!r}")

    exception_text = None
    try:
        param.textValue = "6 in"
        log("  Assignment did not raise.")
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"
        log(f"  Exception: {exception_text}")

    param2 = design.userParameters.itemByName(TEST_PARAM_NAME)
    after = _snapshot(param2) if param2 else {"unit": "PARAM GONE", "expression": "", "token": ""}
    log(f"  After:  unit={after.get('unit')!r}  expression={after.get('expression')!r}")
    log(f"  Unit changed:  {_unit_changed(before, after)}")
    log(f"  Token stable:  {_tokens_match(before, after)}")
    log(f"  Exception:     {exception_text or 'None'}")
    _delete_test_param(design)
    return {"attempt": 7, "unit_changed": _unit_changed(before, after),
            "token_stable": _tokens_match(before, after), "exception": exception_text}


def attempt_control_comment(design, log):
    log("")
    log("=" * 60)
    log("ATTEMPT 8: Control test — comment write (known writable property)")
    log("           Confirms the param object and write path work at all.")
    log("=" * 60)
    param = _create_test_param(design)
    before = _snapshot(param)
    log(f"  Before: comment={before['comment']!r}  unit={before['unit']!r}")

    exception_text = None
    try:
        param.comment = "control_write_succeeded"
        log("  param.comment write did not raise.")
    except Exception as exc:
        exception_text = f"{type(exc).__name__}: {exc}"
        log(f"  Exception: {exception_text}")

    param2 = design.userParameters.itemByName(TEST_PARAM_NAME)
    after = _snapshot(param2) if param2 else {"unit": "PARAM GONE", "expression": "", "token": ""}
    comment_after = param2.comment if param2 else "N/A"
    log(f"  After comment: {comment_after!r}  (expected 'control_write_succeeded')")
    log(f"  Comment write worked: {comment_after == 'control_write_succeeded'}")
    log(f"  Unit changed:  {_unit_changed(before, after)}  (should be False)")
    log(f"  Token stable:  {_tokens_match(before, after)}  (should be True)")
    log(f"  Exception:     {exception_text or 'None'}")
    _delete_test_param(design)
    return {"attempt": 8, "control": True, "comment_write_worked": comment_after == "control_write_succeeded",
            "exception": exception_text}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    design = adsk.fusion.Design.cast(app.activeProduct)

    if not design:
        ui.messageBox("No active Fusion design. Open a document first.")
        return

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILENAME)
    lines = []

    def log(text=""):
        lines.append(str(text))

    log("unit_change_force_attempt.py")
    log(f"Run at: {datetime.datetime.now().isoformat()}")
    log(f"Document: {app.activeDocument.name}")
    log(f"Test parameter: '{TEST_PARAM_NAME}'  start unit: {TEST_UNIT_START!r}  target unit: {TEST_UNIT_TARGET!r}")
    log("")

    results = []
    attempts = [
        attempt_direct_assignment,
        attempt_expression_with_unit,
        attempt_value_assignment,
        attempt_all_parameters_ref,
        attempt_object_inspection,
        attempt_expression_coercion_read,
        attempt_text_value_assignment,
        attempt_control_comment,
    ]

    for fn in attempts:
        try:
            result = fn(design, log)
            results.append(result)
        except Exception as exc:
            log(f"  !! Unhandled error in {fn.__name__}: {exc}")
            log(traceback.format_exc())
            results.append({"attempt": fn.__name__, "unhandled_error": str(exc)})

    # Ensure test param is cleaned up no matter what
    _delete_test_param(design)

    # Summary table
    log("")
    log("=" * 60)
    log("SUMMARY")
    log("=" * 60)
    log(f"  {'#':<4} {'Attempt':<42} {'Unit changed':<14} {'Token stable':<14} {'Exception'}")
    log(f"  {'-'*4} {'-'*42} {'-'*14} {'-'*14} {'-'*30}")
    labels = [
        "Direct unit assignment",
        "Expression with embedded unit",
        "Numeric value assignment",
        "Via allParameters reference",
        "Object inspection (informational)",
        "Expression coercion unit read",
        "textValue assignment",
        "Control: comment write",
    ]
    for i, r in enumerate(results):
        label = labels[i] if i < len(labels) else str(r.get("attempt", "?"))
        if r.get("informational") or r.get("skipped"):
            log(f"  {i+1:<4} {label:<42} {'N/A':<14} {'N/A':<14} (see detail above)")
        else:
            uc = str(r.get("unit_changed", "?"))
            ts = str(r.get("token_stable", "?"))
            ex = r.get("exception") or "None"
            if len(ex) > 50:
                ex = ex[:47] + "..."
            log(f"  {i+1:<4} {label:<42} {uc:<14} {ts:<14} {ex}")

    log("")
    log("END OF REPORT")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    ui.messageBox(f"Done. Results written to:\n{output_path}")
