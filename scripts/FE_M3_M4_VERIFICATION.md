# FE Verification Matrix (Current)

This file documents the current automated FE checks and the final manual-only list where Fusion-native behavior cannot be reliably automated.

## 1) Automated suites

Run from repo root:
- `python -m pytest tests/test_fe_current_baseline.py -q`
- `python -m pytest tests/test_fe_browser_current.py -q` (requires Playwright)

Coverage:
- baseline wiring:
  - harness -> active palette path
  - mock fixture path from `devtools/`
  - Ctrl/Cmd shortcut parity wiring
  - required core control IDs
- browser behavior checks:
  - palette loads in harness
  - layout-debug shortcut toggle path
  - timeline sort disabled when row is dirty
  - apply-all disabled when invalid dirty expression exists
  - discard-all clears dirty state for edited rows

Fusion action-level automation:
- `python scripts/fusion_bp_test_harness.py` (run inside Fusion Scripts)
- validates backend action semantics/state envelopes for copy/delete/timeline/import/export flows.

## 2) Final manual-only list (not fully automatable)

These require live Fusion UI/runtime behavior and remain manual by design:
- actual Fusion palette docking/position behavior across monitor/RDP geometry changes
- true Fusion recompute timing/performance feel under real model complexity
- native Fusion file/data-panel picker interactions and cancellation UX
- visual parity/readability in Fusion-hosted WebView (font/render differences vs standalone browser)
- toolbar/ribbon discoverability and command placement in Fusion workspace contexts
- live model side-effects that depend on Fusion document state and external references

## 3) Execution order for release confidence

1. Run `python -m pytest` (includes baseline FE tests).
2. Run FE browser suite where Playwright is available.
3. Run Fusion harness in Fusion.
4. Run the manual-only list above for release candidates.
