# BetterParameters - Canonical Operational Handoff

Use this prompt as the source of truth for future work on this project.

## System Context

You are taking responsibility for Fusion 360 Python add-in called BetterParameters. Product is modeless HTML palette for editing user parameters. Python↔JS bridge: `palette.sendInfoToHTML(action, data)` → JS handler; JS→Python via `window.adsk.fusionSendData(action, JSON)` → Python handler. All `adsk.*` API calls must be on the main thread.

## Project Scope

- Add-in name: `BetterParameters`
- Source root:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters`
- Live Fusion load root:
  - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\BetterParameters`
  - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/BetterParameters`
- Workspace root:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters`
- Repo: `git@github.com:macifoxispurple/FusionBetterParameters.git`
- Main files:
  - Frontend: `palette.html`
  - Backend: `BetterParameters.py`
  - Manifest: `BetterParameters.manifest`
- Session continuity log:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\scripts\CONTEXT.md`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/scripts/CONTEXT.md`

## Maintainer Quick Start

### Prerequisites

- Git
- Python 3.11+
- `pytest` (`python -m pip install pytest`)
- (Release only) GitHub CLI `gh`
- (Optional local sync) Autodesk Fusion 360 installed

### Repo layout

- `BetterParameters/`: runtime add-in payload (backend/frontend/manifest/resources)
- `tests/`: offline test suite + stubs + manual-only test checklist
- `scripts/`: release + Fusion harness tooling
- `pytest.ini`: pytest discovery config

### First run

From repo root:

```powershell
python -m pytest
```

### FE browser tests (optional but recommended)

Install once:

```powershell
python -m pip install playwright
python -m playwright install chromium
```

Run:

```powershell
python -m pytest tests/test_fe_browser_current.py -q
```

## Non-Negotiable Rules

- Never place packaged release zips inside `BetterParameters` source dir.
- Never place release staging folders inside `BetterParameters` source dir.
- Canonical artifact locations are:
  - Staging dir:
    - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\_release_stage`
    - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/_release_stage`
  - Packaged zips:
    - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\_releases_packages`
    - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/_releases_packages`
- Do not manually edit user data files:
  - `settings.json`
  - `update_state.json`

## Documentation Discipline

- Update `scripts/HANDOFF.md` immediately any time canonical conditions or operational procedures change.
- Keep internal ship/release process documentation in `scripts/HANDOFF.md` only.
- Commit messages must not include extra attribution trailers (for example `Co-Authored-By`, AI/vendor attribution, or tool-brand signatures) unless the user explicitly requests them.
- Use `scripts/CONTEXT.md` for volatile execution state (current task, in-progress, blockers, recent done).
- At startup, read `scripts/CONTEXT.md` after `scripts/HANDOFF.md` before beginning work.
- Update `scripts/CONTEXT.md` at minimum:
  - When starting a new task
  - After meaningful milestones
  - Before pausing, handing off, or ending with incomplete work
- Keep maintainer procedure docs centralized in `scripts/HANDOFF.md`.
- Keep manual-only test checklist in `tests\MANUAL_TESTS.md`.

## BE Test Suite

### Location and tooling

- Tests:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\tests\`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/tests/`
- Config:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\pytest.ini`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/pytest.ini`
- Runner: `python -m pytest` from workspace root
- Stubs: `tests\stubs\adsk\` — minimal offline replacements for `adsk.core` / `adsk.fusion`
- Helpers: `tests\helpers.py` — shared mock factories (`make_mock_design`, `make_package_json`, etc.)

**Isolation rule:** No test files, stub files, `pytest.ini`, or test artifacts may appear inside `BetterParameters\`. The sync command does not touch workspace root files, so this is enforced by directory structure.

### When to add tests

Add or extend tests for any BE change that introduces:
- A new action handler
- New parsing, validation, or normalization logic
- A new data format (package schema, CSV variant, etc.)
- A bug fix where the bug was not previously caught offline

Tests are not required for changes that are purely Fusion API calls with no offline-testable logic (e.g. a handler that only calls `design.userParameters.add` with already-validated inputs). Use judgment — if the logic branches, test the branches.

### Passing gate

All tests must pass before a BE implementation is considered complete. Run the suite after every BE code change:

```powershell
python -m pytest
```

Expected output: `N passed` with no failures or errors. Fix any failures before proceeding to sync, Fusion validation, or ship.

## FE Maintenance And Fusion Harness

### Shared ownership and maintenance (canonical)

- FE changes are owned end-to-end in `palette.html`, including bridge contracts, UX behavior, and regression prevention.
- The Fusion in-process harness is **joint FE+BE responsibility**:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\scripts\fusion_bp_test_harness.py`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/scripts/fusion_bp_test_harness.py`
- Ownership model:
  - FE owns harness alignment with FE-visible workflows, gating, and UX-critical behavior.
  - BE owns harness alignment with backend action semantics, envelope fields, `errorCode`, and contract/schema changes.
  - Any engineer changing FE or BE behavior that affects harness assertions must update harness in the same change.
- Harness updates are required whenever action contracts, response fields, or test-critical FE/BE flows change (for example: `errorCode`, `dryRun`, new actions).
- Keep harness code in `scripts\` (repo tooling), not in runtime add-in payload files.

### FE/Fusion validation procedure

- For FE-affecting work, run both:
  1. Offline suite from workspace root:
     - `python -m pytest`
  2. Fusion in-process harness in Fusion Scripts and Add-Ins:
     - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\scripts\fusion_bp_test_harness.py`
     - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/scripts/fusion_bp_test_harness.py`
- Confirm harness summary reports zero failures before considering FE work complete.
- For manual-only Fusion checks, use:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\tests\MANUAL_TESTS.md`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/tests/MANUAL_TESTS.md`

### Mock bridge policy (FE)

- Mock bridge remains for dev/offline FE iteration only.
- It must be explicit opt-in (`?mock=1` / `window.__BP_USE_MOCK_BRIDGE`).
- It must stay unreachable during normal Fusion runtime when `adsk.fusionSendData` is available.
- Keep the mock path non-production and non-authoritative for release decisions.

### Harness sync to live Fusion Scripts (required)

- Trigger condition: any edit to:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\scripts\fusion_bp_test_harness.py`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/scripts/fusion_bp_test_harness.py`
- Required action: copy updated harness script into Fusion live Scripts directory before Fusion-side test execution.
- Canonical command:

```powershell
Copy-Item -LiteralPath "$env:USERPROFILE\Documents\Codex\BetterParameters\BetterParameters\scripts\fusion_bp_test_harness.py" -Destination "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\Scripts\fusion_bp_test_harness.py" -Force
```

- Verification command (required):

```powershell
$src = "$env:USERPROFILE\Documents\Codex\BetterParameters\BetterParameters\scripts\fusion_bp_test_harness.py"
$dst = "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\Scripts\fusion_bp_test_harness.py"
(Get-FileHash $src).Hash -eq (Get-FileHash $dst).Hash
```

- Expected verification result: `True`.
- Do not run Fusion harness validation against a stale copy in `API\Scripts`.

- macOS canonical commands:

```bash
cp "$HOME/Documents/Codex/BetterParameters/BetterParameters/scripts/fusion_bp_test_harness.py" "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/fusion_bp_test_harness.py"
```

```bash
src="$HOME/Documents/Codex/BetterParameters/BetterParameters/scripts/fusion_bp_test_harness.py"
dst="$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts/fusion_bp_test_harness.py"
[ "$(shasum -a 256 "$src" | awk '{print $1}')" = "$(shasum -a 256 "$dst" | awk '{print $1}')" ] && echo True || echo False
```

### Harness output + clipboard behavior

- On completion, harness now:
  - auto-copies the test summary to clipboard
  - writes a timestamped text report file
  - shows clipboard/report status in the message-box header
- Clipboard success is verification-based:
  - macOS path: `pbcopy` + `pbpaste` equality check
  - primary path: PowerShell `Set-Clipboard` + `Get-Clipboard` equality check
  - fallback path: `clip.exe` + `Get-Clipboard` equality check
  - success is reported only when verification matches.
- Summary body now starts with a run timestamp line:
  - `timestamp: YYYY-MM-DD HH:MM:SS AM/PM`
- Report location is relative to the executing script location:
  - when run from live Fusion Scripts path, reports are written to:
    - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\_harness_reports\`
    - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/_harness_reports/`
- Environment overrides:
  - `BP_HARNESS_BP_PATH`: explicit `BetterParameters.py` path for module load.
  - `BP_HARNESS_REPORT_DIR`: explicit report output directory.

### Debug Hub message logging policy

- Session Message Log:
  - Always available in Debug Hub (`Message Log (Session)`), in-memory only.
- Raw Event Trace (session):
  - Optional, off by default (`Raw Event Trace (Session)`).
  - Captures literal FE/BE traffic and status events for deep diagnostics.
  - Bounded in-memory ring (`1200` entries, payload truncation at `8000` chars per entry).
  - No disk persistence by default.
- Persistent debug capture:
  - Opt-in only (default OFF).
  - Enabled/disabled from Debug Hub `Capture: On/Off` control.
  - Storage: browser local storage (`bp_debug_capture_log_v1`), not always-on file logging.
  - Bounded retention:
    - max entries: `500`
    - max aggregate size: ~`200k` chars
    - max age: `14` days (older entries are pruned automatically)
  - Redaction: obvious local filesystem paths and email-like strings are sanitized before persistence.
  - Export/Clear controls are available in Debug Hub (`Export Capture`, `Clear Capture`).

### Completion gate (all changes)

- No change is complete until all applicable tests pass:
  - BE/offline: `python -m pytest`
  - FE/live Fusion: `fusion_bp_test_harness.py` + targeted manual Fusion validation for touched UX paths
- If harness script changed, completion additionally requires successful live script copy + hash verification step above.
- Do not ship when any applicable test/harness check is failing.

### What is covered

| Test file | Covers |
|---|---|
| `test_bpmeta_parse.py` | `_parse_bpmeta_package` |
| `test_bpmeta_knobs.py` | `_normalized_conflict_policy`, `_extract_apply_knobs` |
| `test_csv.py` | `_serialize_parameters_to_csv`, `_parse_parameters_csv` |
| `test_group_and_metadata.py` | `_normalize_group_name`, metadata value normalizers |
| `test_parameter_name.py` | `_validate_parameter_name_response` (offline portion) |
| `test_export_package.py` | `_export_parameters_package` record shape and field inclusion |
| `test_validate_package_import.py` | `_validate_parameters_package_import` logic |
| `test_import_package.py` | `_import_parameters_package` accounting and ok semantics |
| `test_error_codes.py` | `BPError` hierarchy, all `ERROR_*` constants, action list membership |
| `test_dependency_graph.py` | `_get_parameter_dependency_graph` nodes, edges, token filtering |
| `test_dry_run.py` | `dry_run=True` on `_import_parameters` and `_import_parameters_package` — no mutation, correct counts |
| `test_contract_info.py` | `_get_backend_contract_info` shape and values |
| `test_seed_reset.py` | `_seed_test_parameters`, `_reset_test_state` prefix enforcement, confirm guard, deletion |
| `test_find_by_token.py` | `_find_user_parameter_by_token`, `_find_model_parameter_by_token` with `ObjectCollection` (regression for `isinstance(list\|tuple)` bug) |

### Stub maintenance

If a new BE change uses an `adsk.*` class or constant not yet in the stubs, add it to `tests\stubs\adsk\core.py` or `tests\stubs\adsk\fusion.py` before writing tests. Keep stubs minimal — only the surface area actually needed.

## Dev/Test Loop

After every BE code edit:

1. Run offline test suite and confirm all pass:
```powershell
python -m pytest
```
2. Sync source to live add-in and verify core files:
```powershell
python .\update_helper.py . "$env:APPDATA\Autodesk\Autodesk Fusion 360\API\AddIns\BetterParameters" settings.json update_state.json _pending_update .gitignore __pycache__ BetterParameters.manifest --verify
```

```bash
python3 ./update_helper.py . "$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/BetterParameters" settings.json update_state.json _pending_update .gitignore __pycache__ BetterParameters.manifest --verify
```
Expected output ends with `VERIFY OK` for `BetterParameters.py` and `palette.html` and exit code 0.
If exit code is non-zero or any `VERIFY FAIL` line appears, do not proceed — fix the sync error first.

3. In Fusion 360: Stop add-in, Run add-in, test in an open document with user parameters.

### update_helper.py behavior

- Prints `COPY`, `SKIP`, or `ERROR` for every entry processed.
- Prints summary: `Done: N copied, M skipped, K error(s).`
- `--verify` hash-checks `BetterParameters.py` and `palette.html` after sync (manifest excluded — ship script manages its version separately).
- Always skips `.git`, `.gitignore`, and `dev/` at every level (`.git` and `.gitignore` are hardcoded in `ALWAYS_SKIP`; prevents mock fixture files from syncing into live add-in payload).
- Exits non-zero if any file copy failed or any verify check failed.
- All per-file errors are caught and reported; sync continues through errors so the full error set is visible in one run.

## Ship Semver Policy

When user says "ship", pick bump type and apply exactly:

- major ship: `+1.0.0`
- feature ship: `+0.1.0`
- patch ship: `+0.0.1`

If bump type is not stated, ask user to choose major/feature/patch.

## Ship Procedure

Canonical: use one command from workspace root:

```powershell
python .\scripts\ship.py --bump-type <major|feature|patch> --fusion-tested

Do not bypass this flow with manual `gh release create` for production ships.
Manual release creation skips packaging/upload verification and can publish empty-asset releases.
```

### Ship script usage (all modes)

Run from workspace root.

- Windows executable form:
  - `python .\scripts\ship.py ...`
- macOS executable form:
  - `python3 ./scripts/ship.py ...`

Auth startup check (recommended before release work):

- Validate network/auth context with no mutations:
  - `python3 ./scripts/ship.py --check-auth-only --fusion-tested`
- Local push key notes (machine-specific, not committed):
  - `scripts/PUSHNOTES.md` (read before first push attempt on a new session/machine)
- SSH is the default ship auth mode.
- Optional explicit key routing:
  - `python3 ./scripts/ship.py --check-auth-only --fusion-tested --auth-mode ssh --git-ssh-key <path-to-private-key>`
- Optional explicit SSH command override:
  - `python3 ./scripts/ship.py --check-auth-only --fusion-tested --git-ssh-command "ssh -i <path> -o IdentitiesOnly=yes"`

Modes:

1. Normal ship (bump + package + commit/tag + push + optional release):
- Patch:
  - `python3 ./scripts/ship.py --bump-type patch --fusion-tested`
- Feature:
  - `python3 ./scripts/ship.py --bump-type feature --fusion-tested`
- Major:
  - `python3 ./scripts/ship.py --bump-type major --fusion-tested`

2. Normal ship without publishing GitHub release:
- `python3 ./scripts/ship.py --bump-type patch --fusion-tested --skip-release`

3. Normal ship without push (local only):
- `python3 ./scripts/ship.py --bump-type patch --fusion-tested --skip-push --skip-release`

4. Finalize existing tag (post-tag recovery path):
- `python3 ./scripts/ship.py --finalize-existing-tag vX.Y.Z --fusion-tested --notes-file <path-to-notes.md>`

5. Commit-only workflow (no bump/tag/release):
- Use for docs/tests/tooling updates when no release/version bump is desired.
- `python3 ./scripts/ship.py --commit-only --commit-message "Your commit message"`
- Optional no-push local commit:
  - `python3 ./scripts/ship.py --commit-only --commit-message "Your commit message" --skip-push`

6. Plan mode (no mutations; prints resolved paths/actions):
- `python3 ./scripts/ship.py --bump-type patch --fusion-tested --plan`
- `python3 ./scripts/ship.py --commit-only --plan`

7. Auth preflight-only mode (no mutations):
- `python3 ./scripts/ship.py --check-auth-only --fusion-tested`

8. Re-ship in place (rebuild package for an existing version and replace release asset/notes):
- `python3 ./scripts/ship.py --reship-in-place-tag vX.Y.Z --fusion-tested --notes-file <path-to-notes.md>`
- Optional no-push variant (asset/notes update without branch push):
  - `python3 ./scripts/ship.py --reship-in-place-tag vX.Y.Z --fusion-tested --notes-file <path-to-notes.md> --skip-push`

Important preflight behavior:

- `--bump-type` and `--finalize-existing-tag` require `--fusion-tested`.
- `--reship-in-place-tag` requires `--fusion-tested`.
- `--commit-only` does not require `--fusion-tested`.
- Exactly one mode selector is required:
  - `--bump-type` OR `--finalize-existing-tag` OR `--reship-in-place-tag` OR `--commit-only`.
  - Exception: `--check-auth-only` runs standalone and does not require mode selection.
- `--skip-release` skips GitHub release publish, but normal ship mode still performs bump/tag/package steps.
- Auth defaults/overrides:
  - default auth mode is SSH (`--auth-mode ssh`)
  - optional: `--auth-mode gh` or `--auth-mode auto`
  - optional SSH routing: `--git-ssh-key` or `--git-ssh-command` (command takes precedence)


Release notes responsibility (required at ship start):

- Agent drafts release notes first using actual diff/context before final ship.
- If commit history is low-signal or changes are substantial, use curated notes via `-NotesFile`.
- Release notes style is mandatory for every release:
  - dense, high-level, end-user readable summary of actual fixes/features
  - avoid internal implementation detail, test logs, or tool/process narration
  - maximum 3 non-empty lines total (typically: 1 header + up to 2 bullets)
  - prefer plain language outcomes (what changed for users and why it matters)
- Recommended command when curated notes are prepared:

```powershell
python .\scripts\ship.py --bump-type <major|feature|patch> --fusion-tested --notes-file <path-to-notes.md>
```

What script does:

1. Preflight (`git`, `gh`, `python`, auth/network checks, path checks, mode checks, tag collision checks).
  - includes git remote access probe (`git ls-remote --heads origin`) in effective ship auth context
  - includes `gh auth status` when release publishing is enabled
  - includes origin/`--repo-slug` mismatch guard
2. Preflight release-notes preparation/quality gate (before any version bump, commit, tag, or push).
3. Sync source -> live add-in and verify sync hashes for core files.
4. Build + verify deterministic zip in canonical artifact dirs **before bump/tag/push** (staged manifest is rewritten to target release version).
5. Bump source manifest version using semver policy.
6. Commit and create annotated tag.
7. Push branch + tag (unless `-SkipPush`).
8. Create/update GitHub release using `--notes-file` flow.
9. Verify release tag + expected zip asset name.
10. Write machine-readable run report JSON to `scripts\_ship_reports\ship_<timestamp>.json`.

Release notes behavior:

- If `--notes-file` is omitted, `scripts\ship.py` auto-generates non-placeholder highlights from git history/diff between the previous version tag and `HEAD`.
- If generated highlights are low-signal (only diff-stat/file-list style bullets), ship now fails in **preflight** and requires `--notes-file` with curated notes.
- If `--notes-file` is omitted and `scripts\release_notes_pending.md` exists, ship uses that file automatically.
- `scripts\release_notes_template.md` should use `{{AUTO_HIGHLIGHTS}}` where generated bullets should be inserted.
- If a template with legacy placeholder text (`<feature 1>`, etc.) is detected, ship script replaces it with generated highlights automatically.

Release existence behavior:

- `scripts\ship.py` treats `gh release view <tag>` "release not found" as a normal non-error probe result.
- If release does not exist, script continues and creates it automatically (no manual recovery step needed).

Finalize/recovery mode:

- `scripts\ship.py` supports release-finalization mode for post-tag recovery:
  - `python .\scripts\ship.py --finalize-existing-tag vX.Y.Z --fusion-tested --notes-file <path-to-notes.md>`
- Finalize mode does not bump version, commit, tag, or push.
- Finalize mode performs:
  - release-notes preflight preparation
  - existing zip verification (`BetterParameters-X.Y.Z.zip` manifest/version/root-shape checks)
  - create/update GitHub release + asset upload/verification

Re-ship in place mode:

- `scripts\ship.py` supports explicit same-version re-ship mode:
  - `python .\scripts\ship.py --reship-in-place-tag vX.Y.Z --fusion-tested --notes-file <path-to-notes.md>`
- Re-ship mode is intended when you need to replace the already-published asset/notes for an existing release tag.
- Re-ship mode does not bump version, create a release commit, or create/push a new tag.
- Re-ship mode performs:
  - optional source -> live add-in sync (same behavior as normal ship when live root is provided)
  - deterministic package rebuild for `X.Y.Z` from current source state
  - branch push (unless `--skip-push`)
  - create/update GitHub release + asset upload/verification for the existing tag

Push-failure recovery behavior:

- If push fails after local release commit/tag creation, ship now prints explicit recovery commands:
  - push branch
  - push tag
  - finalize existing tag with `--finalize-existing-tag ... --notes-file ...`

Packaging resiliency behavior:

- Zip build now retries with lock checks before archive creation.
- If `Compress-Archive` fails repeatedly, script falls back to `.NET ZipFile.CreateFromDirectory(...)`.
- On failure, script reports locked-file hints (when detectable) and prints a finalize-mode recovery command.

Version consistency requirements:

- Manifest version must be `X.Y.Z`.
- Git tag must be `vX.Y.Z`.
- Zip filename must include same version token, format:
  - `BetterParameters-X.Y.Z.zip`

## Packaging Procedure (Canonical Paths)

Use these paths for release packaging:

- Stage root:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\_release_stage`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/_release_stage`
- Stage package folder:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\_release_stage\BetterParameters`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/_release_stage/BetterParameters`
- Zip output:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\_releases_packages\BetterParameters-X.Y.Z.zip`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/_releases_packages/BetterParameters-X.Y.Z.zip`

Do not leave stale stage content. Recreate stage folder fresh per release.

Canonical script paths:

- Canonical ship script:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\scripts\ship.py`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/scripts/ship.py`
- Release notes template:
  - Windows: `%USERPROFILE%\Documents\Codex\BetterParameters\BetterParameters\scripts\release_notes_template.md`
  - macOS: `~/Documents/Codex/BetterParameters/BetterParameters/scripts/release_notes_template.md`

## GitHub Release Notes Formatting (Required)

Do not pass release notes as one-line text with literal `\n`.
That causes broken formatting and rework.

Always write real multiline notes and pass with `--notes-file`.

Safe PowerShell pattern:

```powershell
$ver = "X.Y.Z"
$tag = "v$ver"
$zip = "$env:USERPROFILE\Documents\Codex\BetterParameters\BetterParameters\_releases_packages\BetterParameters-$ver.zip"
$notes = @'
BetterParameters vX.Y.Z

Highlights:
- Item 1
- Item 2
'@
$tmp = Join-Path $env:TEMP "bp_release_notes_$ver.md"
[System.IO.File]::WriteAllText($tmp, $notes, (New-Object System.Text.UTF8Encoding($false)))
gh release create $tag $zip --repo macifoxispurple/FusionBetterParameters --title $tag --notes-file $tmp
Remove-Item $tmp -Force
```

macOS equivalent:

```bash
ver="X.Y.Z"
tag="v$ver"
zip="$HOME/Documents/Codex/BetterParameters/BetterParameters/_releases_packages/BetterParameters-$ver.zip"
tmp="$(mktemp /tmp/bp_release_notes_${ver}_XXXX.md)"
cat > "$tmp" <<'EOF'
BetterParameters vX.Y.Z

Highlights:
- Item 1
- Item 2
EOF
gh release create "$tag" "$zip" --repo macifoxispurple/FusionBetterParameters --title "$tag" --notes-file "$tmp"
rm -f "$tmp"
```

For existing release edits:

```powershell
gh release edit vX.Y.Z --repo macifoxispurple/FusionBetterParameters --notes-file <path-to-notes.md>
```

## Final Ship Checklist

- Offline test suite passes (`python -m pytest`).
- Manifest updated.
- Sync to live performed.
- Tests done in Fusion.
- Commit created.
- Tag created.
- Branch pushed.
- Tag pushed.
- Zip created in `_releases_packages`.
- GitHub release has expected versioned ZIP asset attached (`BetterParameters-X.Y.Z.zip`).
- GitHub release created/updated with proper multiline notes.
- Confirm no zip/stage artifacts were created in `BetterParameters` source dir.

## Post-Ship User Notification

- Default post-ship user message should be minimal:
  - `shipped. release: <version link>`
- Do not include extra ship metadata by default (commit, tag, artifact paths, stage paths) unless the user explicitly asks for those details.
