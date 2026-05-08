# BetterParameters Code Health + Performance Review (Hybrid)

Date: 2026-05-08
Reviewer: Codex
Scope: Backend (`BetterParameters.py`), Frontend (`palette.html`), tooling (`scripts/*.py`), tests.

## Method + Baseline
- Static deep scan: function-size hotspots, action-contract paths, repeated logic patterns, legacy/dead-path indicators.
- Runtime proxy profiling: pytest duration baseline + targeted cProfile on model-parameter-heavy test module.
- Full suite baseline: `420 passed, 6 skipped, 0 failed` in `0.42s`.
- FE-focused tests: `3 passed, 6 skipped, 0 failed` in `0.01s`.

### Quantified Hotspot Snapshot
- File size concentration:
  - `BetterParameters/palette.html`: 17,190 LOC
  - `BetterParameters/BetterParameters.py`: 7,316 LOC
- Largest backend functions:
  - `_handle_palette_action`: 348 LOC
  - `_save_settings`: 173 LOC
  - `_import_parameters_package`: 163 LOC
  - `_delete_parameters_batch`: 154 LOC
- Largest frontend functions (named decls):
  - `renderParameters`: 238 LOC
  - `applyAllDirtyRows`: 221 LOC
  - `applyRowDraft`: 196 LOC
  - `buildGroupedParameters`: 171 LOC
  - `applyState`: 164 LOC
- Duplicate-window heuristic (normalized repeated 8-line windows):
  - `palette.html`: 258
  - `BetterParameters.py`: 137
  - `scripts/ship.py`: 12

## Ranked Findings (P0/P1/P2)

### P1-1: Full state rebuild on many mutating actions
- Evidence:
  - `_handle_palette_action` repeatedly returns `_ok_state(_current_state_payload())` across most mutating actions.
  - Same function has 33 `_current_state_payload(...)` call sites in one dispatch block.
  - `_current_state_payload` itself does multiple expensive operations: order sync/read, full parameter collection, group collection, all-parameter-name collection.
- Impact:
  - Scales with design size; likely visible latency for larger parameter sets.
  - Amplifies cost because each mutate action often requests full snapshot even when only one row changed.
- Confidence: High
- Suggested fix shape:
  - Introduce incremental response mode for selected high-frequency actions (row-level patch payload + optional lazy refresh).
  - Keep full payload fallback for contract safety.
- Risk: Medium (contract-sensitive).
- Effort: Medium-Large.

### P1-2: Frontend full-table rerender pipeline is heavy + frequent
- Evidence:
  - `applyState` calls `renderParameters(payload.parameters)` for every state payload with parameters.
  - `renderParameters` rebuilds full `tbody.innerHTML` and then runs additional sweeps (`querySelectorAll`, `updateRowSaveState` per row, placeholders/autosize, preview pass).
  - Single render function is 238 LOC with many per-row string/template operations.
- Impact:
  - Potential UI jank with large datasets, especially after rapid edits or repeated responses.
- Confidence: High
- Suggested fix shape:
  - Add render-diff path (update only touched rows when possible).
  - Coalesce post-render sweeps into one pass.
- Risk: Medium.
- Effort: Medium-Large.

### P1-3: Action taxonomy duplication risks drift
- Evidence:
  - `NORMATIVE_ACTIONS`, `MUTATING_ACTIONS`, `READ_ONLY_OR_VALIDATION_ACTIONS` maintain overlapping manual lists.
  - Action additions require multi-list updates; omission risk increases with growth.
- Impact:
  - Contract drift bugs, inconsistent response validation, harder maintenance.
- Confidence: High
- Suggested fix shape:
  - Central action registry with metadata flags (`mutates`, `stateOptional`, `readOnly`).
- Risk: Low.
- Effort: Small-Medium.

### P1-4: Dispatch giant function complexity + repetitive envelopes
- Evidence:
  - `_handle_palette_action` is 348 LOC and many branches duplicate response envelope assembly for cancel/dry-run/state patterns.
- Impact:
  - Higher bug surface for new actions; inconsistent envelope handling more likely.
- Confidence: High
- Suggested fix shape:
  - Table-driven dispatch + shared envelope helpers for common patterns.
- Risk: Medium (behavior preservation required).
- Effort: Medium.

### P2-1: Duplicate FE markup generation in row render
- Evidence:
  - `favoriteButtonMain` and `favoriteButtonNarrow` build nearly identical HTML with duplicated branch logic.
  - Similar repeated string templates for row action buttons and field shells.
- Impact:
  - Maintenance noise, increases chance of divergent behavior/styling bugs.
- Confidence: High
- Suggested fix shape:
  - Extract mini render helpers for repeated fragments.
- Risk: Low.
- Effort: Small.

### P2-2: Legacy-path retention candidates
- Evidence:
  - Backend has explicit legacy migration/storage path functions (`_legacy_document_order_root`, `_migrate_legacy_document_order_dir`).
  - FE carries `legacy:` group-key handling pathways.
- Impact:
  - More branch complexity and test load; possible dormant behavior.
- Confidence: Medium
- Suggested fix shape:
  - Add telemetry/log counter or test evidence gate; remove only when no live dependency remains.
- Risk: Medium (compatibility-sensitive).
- Effort: Small-Medium.

### P2-3: Test profile blind spot for large-scale performance
- Evidence:
  - Suite extremely fast (`0.42s`) and FE browser tests mostly skipped (6 skipped).
  - cProfile on model tests shows logic hotspots (`_get_model_parameters`, `_serialize_model_parameter`, `_format_parameter_value`) but only on mocked/small-scale data.
- Impact:
  - Real-world perf regressions can slip through despite green tests.
- Confidence: High
- Suggested fix shape:
  - Add large-fixture perf smoke tests (non-flaky thresholds, trend-based checks).
- Risk: Low.
- Effort: Medium.

## Duplicate / Dead / Redundancy Map
- High-confidence duplicates:
  - FE action set declarations (`NORMATIVE_ACTIONS` vs `MUTATING_ACTIONS` overlaps).
  - FE row-fragment HTML duplication in `renderParameters`.
  - BE response-envelope boilerplate across import/export/cancel branches.
- Potential abandoned/legacy:
  - Legacy document order migration path.
  - Legacy group-key canonicalization paths in FE.
- Redundancy in flow:
  - Repeated full-state recomputation after many single-record mutations.

## Remediation Backlog

### Quick Wins (low risk / high ROI)
1. Unify FE action metadata into one registry object.
2. Extract FE row-fragment helper builders to remove duplicate HTML branches.
3. Introduce BE envelope helper functions for cancel/dry-run/state payload patterns.
4. Add lightweight counters/timers (guarded by debug flag) around `renderParameters` and `_current_state_payload`.

### Structural Refactors (staged)
1. BE dispatch refactor to table-driven handler map with standardized response policy.
2. Incremental state update path for high-frequency actions (edit/revert/favorite/group/name).
3. FE partial row-update rendering path to avoid full-table rerender for single-row changes.
4. Legacy-path retirement plan with compatibility checkpoint (instrument -> observe -> remove).

### Deferred / No-action (for now)
1. `scripts/ship.py` architecture: acceptable at current size; keep as-is pending feature growth.
2. Harness refactor: currently moderate size and low duplicate density; revisit after runtime path changes.

## Validation Plan Per Fix Class
- Contract-sensitive BE changes:
  - full `pytest`; explicit action-envelope regression tests for affected actions.
- FE rendering-path changes:
  - FE baseline tests + browser tests where available + Fusion harness smoke for row edits/group operations.
- Performance-targeted changes:
  - before/after timing for:
    - `_current_state_payload`
    - `_get_model_parameters`
    - `renderParameters`
  - compare on representative small/medium/large parameter fixture sizes.
- Legacy cleanup:
  - migration compatibility tests + explicit rollback strategy.

## Runtime Profiling Coverage Notes
- Completed in this environment:
  - pytest duration baseline
  - targeted cProfile on model-parameter backend path
- Pending live Fusion/browser instrumentation (manual environment step):
  - large document end-to-end timings for mutating actions and rerender frequency.
