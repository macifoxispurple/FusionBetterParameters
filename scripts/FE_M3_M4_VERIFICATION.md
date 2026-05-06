# FE M3/M4 Verification Matrix

Scope: durable verification process for remaining FE roadmap items in `CONTEXT.md` (M3 + M4).

## 1) Automated Coverage

Run inside Fusion:
- Script: `C:\Users\Maci\Documents\Codex\OpenParameters\scripts\fusion_bp_test_harness.py`

What this now verifies:
- M3 Copy
  - auto-name copy by key (`copyParameter`)
  - explicit-name copy by target name
- M3 Delete
  - partial-success delete path (`deleteParameters`) with mixed existing/missing items
- M3 Timeline Sort
  - `sortByTimelineOrder` returns `ok:true`
  - expected relative order for seeded timeline test params (`_bptest_timeline_c -> _bptest_timeline_a -> _bptest_timeline_b`)
- M4 CSV Export
  - `exportParameters` writes a CSV
  - header row shape matches expected contract
- M4 CSV Import
  - dry-run is non-mutating (`state:null`)
  - commit mutates
  - conflict policy behavior
    - `skip` does not overwrite existing expression, still creates new rows
    - `overwrite` updates existing expression
- M4 Apply-All action-level invariant
  - sequential `updateParameter` calls each return `state`
  - dependent expression update path remains valid

Pass criteria:
- Harness summary reports `0 failed`.

Additional FE DOM automation (local/dev):
- File: `C:\Users\Maci\Documents\Codex\OpenParameters\BetterParameters\dev_harness.html`
- Control: `Run FE Regression Tests`

What FE DOM runner verifies:
- Single-row Apply keeps other dirty rows intact.
- Resize preserves dirty drafts.
- Timeline sort is blocked when local edits are dirty (disabled + guidance tooltip).
- CSV import cancel path does not emit error/cancel status noise.
- Package import partial-failure details render in summary.
- Auto mode: blur applies valid edits.
- Auto mode: invalid expression remains dirty with persistent error.
- Auto mode: comment-field discard click clears draft (no unintended apply).
- Manual mode: Apply All disabled when any dirty row is invalid.
- Manual mode: Discard All resets all dirty rows to last-known-good values.

## 2) Manual UI Coverage (required)

The harness does not drive palette DOM interactions. These checks stay manual until dedicated UI automation exists.

M3 manual checks:
- Copy action discoverability in UI for single and multi-select.
- Delete action confirm prompt text and selected-count accuracy.
- Timeline sort command blocked when unsaved edits exist, with visible attention message.

M4 manual checks:
- Export/import controls and user messaging readability.
- Manual: row Apply only applies that row; other dirty rows remain queued.

## 3) Execution Order (for FE completion)

1. Run Fusion harness and record result.
2. Run manual UI checklist for current change set.
3. If any fail, fix and re-run both.
4. Only mark task complete in `CONTEXT.md` when both automated + manual checks pass.

## 4) Known Limits

- This script validates action semantics and state envelopes, not visual layout correctness.
- Full row-level UI behavior requires future DOM automation (separate project).
