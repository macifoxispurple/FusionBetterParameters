# Contributing

## Prerequisites

- Git
- Python 3.11+
- `pytest` (`python -m pip install pytest`)
- (Release only) GitHub CLI `gh`
- (Optional local Fusion sync) Autodesk Fusion 360 installed

## Setup (Windows or macOS)

1. Clone repo.
2. Open terminal at repo root.
3. Run tests:

```bash
python -m pytest
```

## Development Workflow

- Runtime source lives under `BetterParameters/`.
- Tests live under `tests/`.
- Keep runtime/build artifacts untracked (`.gitignore` enforced).

## Sync to Live Fusion Add-In (example)

```bash
python BetterParameters/update_helper.py BetterParameters "<LIVE_ADDIN_PATH>" settings.json update_state.json _pending_update .gitignore __pycache__ BetterParameters.manifest --verify
```

Expected verify lines:
- `VERIFY OK BetterParameters.py`
- `VERIFY OK palette.html`

## Release Flow (Windows, PowerShell)

From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ship.ps1 -BumpType patch -FusionTested
```

### Script parameters for portability

- `-WorkspaceRoot` defaults to repo root.
- `-SourceRoot` defaults to `<WorkspaceRoot>/BetterParameters`.
- `-LiveAddinRoot` can be set explicitly or via `BP_LIVE_ADDIN_ROOT` env var.

## Secret/Privacy Hygiene

- Do not commit tokens, keys, certs, env files, or machine-local paths.
- Optional scan config: `.gitleaks.toml`.