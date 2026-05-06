# BetterParameters Repository

Fusion 360 add-in for fast user-parameter editing with a modeless palette.

## Repo Layout

- `BetterParameters/`: runtime add-in payload (Python backend + HTML frontend + manifest/resources).
- `tests/`: offline backend test suite and Fusion API stubs.
- `scripts/`: shipping, validation harness, and release tooling.
- `pytest.ini`: pytest discovery config.
- `BACKEND_API.md`: backend action/contract reference.

## Quick Start

1. Install Python 3.11+.
2. From repo root, run:

```powershell
python -m pytest
```

## Generated vs Committed

| Item | Committed | Notes |
|---|---|---|
| `BetterParameters/*` runtime source | Yes | Includes `update_helper.py` and `update_state.py`. |
| `tests/*` and stubs | Yes | Required for offline validation. |
| `scripts/*` tooling | Yes | Ship + harness scripts. |
| `settings.json`, `update_state.json`, `_pending_update/` | No | Local runtime state. |
| `_release_stage/`, `_releases_packages/`, `scripts/_ship_reports/` | No | Generated release artifacts/reports. |
| `__pycache__/`, `.pytest_*`, temp dirs | No | Machine-generated cache files. |

## Cross-Platform Notes

- Text files are normalized via `.gitattributes` + `.editorconfig`.
- Use repo-relative commands where possible.
- Windows-specific live Fusion sync/deploy paths are parameterized in scripts.

See `CONTRIBUTING.md` for setup and workflow details.