# Manual Fusion Tests (Non-Automatable)

These checks require live Fusion runtime/UI behavior and are intentionally manual.

## Required manual checks

- Palette docking/position recovery across monitor or RDP geometry changes.
- Real-model recompute timing/performance feel under realistic model complexity.
- Native Fusion data/file picker interactions, including cancellation behavior.
- Visual readability/parity in Fusion-hosted WebView (font/render differences versus standalone browser).
- Toolbar/ribbon discoverability and command placement across Fusion workspace contexts.
- Live model side-effects that depend on current document state and external references.

## Release confidence order

1. Run `python -m pytest`.
2. Run browser FE tests (Playwright) when available:
   - `python -m pytest tests/test_fe_browser_current.py -q`
3. Run Fusion action harness in Fusion:
   - `python scripts/fusion_bp_test_harness.py`
4. Execute the manual checks above in a live Fusion session.
