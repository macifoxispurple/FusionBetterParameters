# BetterParameters - Compact Canonical Handoff

Use this as the operational source of truth.

## 1. Core Context

- Project: Fusion 360 Python add-in `BetterParameters`
- UI: modeless HTML palette for editing user parameters
- Frontend: `palette.html`
- Backend: `BetterParameters.py`
- Manifest: `BetterParameters.manifest`
- Repo: `git@github.com:macifoxispurple/FusionBetterParameters.git`
- Bridge:
  - Python -> JS: `palette.sendInfoToHTML(action, data)`
  - JS -> Python: `window.adsk.fusionSendData(action, JSON)`
- Rule: all `adsk.*` API calls must run on Fusion main thread

## 2. Path Aliases

Use these aliases to avoid repeating platform-specific roots.

### Windows

- `WS`: `%USERPROFILE%\Documents\Codex\BetterParameters`
- `LIVE_ADDIN`: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\BetterParameters`
- `LIVE_SCRIPTS`: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\Scripts`
- `HARNESS_REPORTS`: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\_harness_reports`

### macOS

- `WS`: `~/Documents/Codex/BetterParameters`
- `LIVE_ADDIN`: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/BetterParameters`
- `LIVE_SCRIPTS`: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts`
- `HARNESS_REPORTS`: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/_harness_reports`

### Canonical repo paths

- Runtime payload: `WS/BetterParameters/`
- Tests: `WS/tests/`
- Scripts/tools: `WS/scripts/`
- Context log: `WS/scripts/CONTEXT.md`
- Handoff: `WS/scripts/HANDOFF.md`
- Fusion harness: `WS/scripts/fusion_bp_test_harness.py`
- Pytest config: `WS/pytest.ini`

## 3. Quick Start

Prereqs: Git, Python `3.11+`, `pytest`, `gh` for release work, Fusion 360 optional for live validation.

Repo layout:

- `BetterParameters/`: runtime payload
- `tests/`: offline tests, stubs, manual checklist
- `scripts/`: ship/release/Fusion tooling

Run from workspace root:

```bash
python -m pytest
```

Optional FE browser test setup:

```bash
python -m pip install playwright
python -m playwright install chromium
python -m pytest tests/test_fe_browser_current.py -q
```

## 4. Non-Negotiables

- Never place packaged release zips inside `BetterParameters/`
- Never place release staging folders inside `BetterParameters/`
- Canonical artifact dirs:
  - Stage root: `WS/_release_stage`
  - Zip output: `WS/_releases_packages`
- Never manually edit:
  - `settings.json`
  - `update_state.json`
- Commit messages must not include attribution trailers unless user explicitly asks

## 5. Documentation Discipline

- If canonical procedures change, update `scripts/HANDOFF.md` immediately
- Keep ship/release procedure docs in `scripts/HANDOFF.md` only
- Use `scripts/CONTEXT.md` for volatile state: current task, progress, blockers, recent work
- At startup: read `scripts/HANDOFF.md`, then `scripts/CONTEXT.md`
- Update `scripts/CONTEXT.md`:
  - at task start
  - after meaningful milestones
  - before pause/handoff/ending with incomplete work
- Manual-only checklist lives at `tests/MANUAL_TESTS.md`

## 6. Backend Test Rules

- Offline runner: `python -m pytest`
- Stubs: `tests/stubs/adsk/`
- Shared helpers: `tests/helpers.py`
- Isolation rule: no tests, stubs, `pytest.ini`, or artifacts inside `BetterParameters/`
- Add/extend tests for new handlers, parsing/validation/normalization, new data formats, and bug fixes not previously caught
- Skip tests only for logic-free Fusion API pass-through code; if logic branches, test it
- If new `adsk.*` surface is needed, update `tests/stubs/adsk/core.py` or `tests/stubs/adsk/fusion.py`, minimally
- BE completion gate: `python -m pytest` must pass

## 7. FE + Fusion Harness Rules

- FE ownership is end-to-end in `palette.html`
- Harness is joint FE+BE responsibility
  - FE: UX-visible workflow/gating alignment
  - BE: action semantics, envelope fields, schema/contract alignment
- If FE/BE changes affect harness assertions, update harness in same change
- Keep harness in `scripts/`, never runtime payload
- FE-affecting work requires:
  1. `python -m pytest`
  2. `scripts/fusion_bp_test_harness.py`
  3. targeted manual Fusion validation for touched UX paths
- Mock bridge is dev/offline only, opt-in only (`?mock=1` or `window.__BP_USE_MOCK_BRIDGE`), must stay unreachable when `adsk.fusionSendData` exists, and does not count as release evidence

## 8. Harness Sync + Output

If `scripts/fusion_bp_test_harness.py` changes, copy it to `LIVE_SCRIPTS` before running Fusion-side tests.

Windows:

```powershell
Copy-Item -LiteralPath "$env:USERPROFILE\Documents\Codex\BetterParameters\scripts\fusion_bp_test_harness.py" -Destination "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\Scripts\fusion_bp_test_harness.py" -Force
```

```powershell
$src = "$env:USERPROFILE\Documents\Codex\BetterParameters\scripts\fusion_bp_test_harness.py"
$dst = "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\Scripts\fusion_bp_test_harness.py"
(Get-FileHash $src).Hash -eq (Get-FileHash $dst).Hash
```

macOS:

```bash
cp "$HOME/Documents/Codex/BetterParameters/scripts/fusion_bp_test_harness.py" "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/fusion_bp_test_harness.py"
```

```bash
src="$HOME/Documents/Codex/BetterParameters/scripts/fusion_bp_test_harness.py"
dst="$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/fusion_bp_test_harness.py"
[ "$(shasum -a 256 "$src" | awk '{print $1}')" = "$(shasum -a 256 "$dst" | awk '{print $1}')" ] && echo True || echo False
```

Required result: `True`

Harness completion behavior:

- auto-copy summary to clipboard
- write timestamped text report
- show clipboard/report status in header
- start summary with `timestamp: YYYY-MM-DD HH:MM:SS AM/PM`
- when run from live Scripts path, write reports to `HARNESS_REPORTS`
- env overrides:
  - `BP_HARNESS_BP_PATH`
  - `BP_HARNESS_REPORT_DIR`
- clipboard success is verification-based:
  - macOS: `pbcopy` + `pbpaste`
  - Windows: `Set-Clipboard`/`Get-Clipboard`, fallback `clip.exe`

## 9. Debug Hub Logging Policy

- `Message Log (Session)`: always available, memory only
- `Raw Event Trace (Session)`: optional, off by default
  - deep FE/BE traffic diagnostics
  - in-memory ring `1200` entries
  - payload truncation `8000` chars per entry
- Persistent capture:
  - opt-in only, default off
  - toggled in Debug Hub `Capture: On/Off`
  - stored in browser local storage `bp_debug_capture_log_v1`
  - bounded retention:
    - `500` entries
    - about `200k` chars aggregate
    - `14` day max age
  - sanitize obvious local paths and email-like strings before persistence
  - controls: `Export Capture`, `Clear Capture`

## 10. Dev/Test Loop

After every BE code edit:

1. Run offline tests:

```bash
python -m pytest
```

2. Sync workspace to live add-in and verify:

Windows:

```powershell
python .\update_helper.py . "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\BetterParameters" settings.json update_state.json _pending_update .gitignore __pycache__ BetterParameters.manifest --verify
```

macOS:

```bash
python3 ./update_helper.py . "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/BetterParameters" settings.json update_state.json _pending_update .gitignore __pycache__ BetterParameters.manifest --verify
```

Expected:

- exit code `0`
- `VERIFY OK` for `BetterParameters.py` and `palette.html`
- no `VERIFY FAIL`

If sync fails, stop and fix it before Fusion validation.

3. In Fusion:

- stop add-in
- run add-in
- test in open doc with user parameters

`update_helper.py` behavior:

- prints `COPY`, `SKIP`, or `ERROR` per entry
- prints `Done: N copied, M skipped, K error(s).`
- `--verify` checks hashes for `BetterParameters.py` and `palette.html`
- always skips `.git`, `.gitignore`, and `dev/`
- exits non-zero on copy or verify failure
- reports all per-file errors without aborting early

## 11. Completion Gate

No change is complete until all applicable checks pass:

- BE/offline: `python -m pytest`
- FE/live Fusion: harness + targeted manual Fusion validation
- If harness changed: live script copy + hash verification also required
- Do not ship with any failing applicable test/harness check

## 12. Ship Semver Policy

When user says "ship":

- `major` -> `+1.0.0`
- `feature` -> `+0.1.0`
- `patch` -> `+0.0.1`

If bump type not given, ask: `major`, `feature`, or `patch`.

## 13. Ship Procedure

Canonical entrypoint from workspace root:

Windows:

```powershell
python .\scripts\ship.py --bump-type <major|feature|patch> --fusion-tested
```

macOS:

```bash
python3 ./scripts/ship.py --bump-type <major|feature|patch> --fusion-tested
```

Do not bypass this with manual `gh release create` for production ships.

### Ship auth + startup notes

- Preflight: `python3 ./scripts/ship.py --check-auth-only --fusion-tested`
- Read `scripts/PUSHNOTES.md` before first push on a new machine/session
- Default auth mode: SSH
- Optional overrides: `--auth-mode ssh|gh|auto`, `--git-ssh-key`, `--git-ssh-command`

### Required mode rules

- `--bump-type`, `--finalize-existing-tag`, and `--reship-in-place-tag` require `--fusion-tested`
- `--commit-only` does not require `--fusion-tested`
- Exactly one mode selector is required:
  - `--bump-type`
  - `--finalize-existing-tag`
  - `--reship-in-place-tag`
  - `--commit-only`
- Exception: `--check-auth-only` runs by itself

### Common modes

- Normal ship: `python3 ./scripts/ship.py --bump-type <patch|feature|major> --fusion-tested`
- Skip GitHub release: add `--skip-release`
- Local only: add `--skip-push --skip-release`
- Commit-only: `python3 ./scripts/ship.py --commit-only --commit-message "..." [--skip-push]`
- Plan: `python3 ./scripts/ship.py --bump-type patch --fusion-tested --plan` or `--commit-only --plan`
- Finalize existing tag: `python3 ./scripts/ship.py --finalize-existing-tag vX.Y.Z --fusion-tested --notes-file <path>`
- Re-ship in place: `python3 ./scripts/ship.py --reship-in-place-tag vX.Y.Z --fusion-tested --notes-file <path> [--skip-push]`

### What ship.py does

1. Preflight tools/auth/network/path/mode/tag checks
2. Release-notes quality gate before mutation
3. Sync source to live add-in and verify core files
4. Build and verify deterministic zip before bump/tag/push
5. Bump manifest version
6. Commit and create annotated tag
7. Push branch and tag unless `--skip-push`
8. Create/update GitHub release
9. Verify release tag and expected zip asset
10. Write `scripts/_ship_reports/ship_<timestamp>.json`

Preflight includes `git`, `gh`, `python`, `git ls-remote --heads origin`, `gh auth status` when release publishing is enabled, origin/`--repo-slug` mismatch guard, and tag collision checks.

### Release notes rules

- Draft notes first from real diff/history
- If history is low-signal or changes are substantial, use curated `--notes-file`
- Required style:
  - dense, high-level, end-user readable
  - actual fixes/features only
  - max `3` non-empty lines
  - no secrets or local machine/user/path/auth/key/token details
  - no implementation/test/process narration
- Recommended: `python3 ./scripts/ship.py --bump-type patch --fusion-tested --notes-file <path>`
- If `--notes-file` is omitted:
  - ship auto-generates notes since previous tag
  - preflight fails if generated notes are low-signal
  - `scripts/release_notes_pending.md` is used automatically if present
  - `scripts/release_notes_template.md` may contain `{{AUTO_HIGHLIGHTS}}`
  - legacy placeholders are auto-replaced
- `gh release view <tag>` not-found is treated as normal; missing release is auto-created

### Recovery / resiliency

Finalize mode:

- no bump, commit, tag, or push
- verify existing `BetterParameters-X.Y.Z.zip`
- create/update GitHub release and asset

Re-ship mode:

- rebuild same version and replace release asset/notes for existing tag
- no new version bump, release commit, or tag
- may sync live add-in first
- may skip branch push

Push failure after local commit/tag:

- ship prints recovery commands for branch push, tag push, and finalize mode

Packaging resiliency:

- zip build retries with lock checks
- if `Compress-Archive` keeps failing, fallback is `.NET ZipFile.CreateFromDirectory(...)`
- failures include locked-file hints when detectable and a finalize recovery command

Version consistency is mandatory: manifest `X.Y.Z`, tag `vX.Y.Z`, zip `BetterParameters-X.Y.Z.zip`.

## 14. Packaging Rules

Canonical paths:

- Stage root: `WS/_release_stage`
- Stage package dir: `WS/_release_stage/BetterParameters`
- Zip output: `WS/_releases_packages/BetterParameters-X.Y.Z.zip`

Rules:

- recreate stage fresh each release
- never leave ship artifacts in `BetterParameters/`
- canonical script: `scripts/ship.py`
- release notes template: `scripts/release_notes_template.md`

## 15. Manual GitHub Release Notes Fallback

- Never use one-line `--notes "...\n..."` for releases
- Always use a real multiline temp file and `--notes-file`
- Keep notes privacy-safe: no secrets or local operational details
- Existing release note edit:

```powershell
gh release edit vX.Y.Z --repo macifoxispurple/FusionBetterParameters --notes-file <path-to-notes.md>
```

## 16. Final Ship Checklist

- offline tests pass
- manifest updated
- sync to live add-in done
- Fusion validation done
- commit created
- tag created
- branch pushed
- tag pushed
- versioned zip exists in `_releases_packages`
- GitHub release has expected zip asset
- release notes are multiline, correct, privacy-safe
- no zip/stage artifacts were created inside `BetterParameters/`

## 17. Post-Ship User Reply

Default minimal reply:

- `shipped. release: <version link>`

Do not include extra ship metadata unless user asks.
