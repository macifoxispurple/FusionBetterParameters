BetterParameters Patch Release

Highlights:
- Fixed silent partial-failure behavior for selected parameter deletes.
- Implemented hybrid delete strategy in backend:
  - dependency-informed ordering (dependents before dependencies)
  - multi-pass retries (up to 10 passes) to incrementally resolve reference chains
  - explicit remaining-failure reporting with parameter-level reasons when deletion cannot complete
- Added delete failure reporting UX in frontend:
  - shared modal report shown only when some selected deletes remain
  - includes requested/deleted/remaining counts plus per-parameter failure details
  - wired for both main selected-delete and row-menu selected-delete paths
- Continued shared modal UX consistency across operations.

Validation:
- `python -m pytest` passed.
- Canonical live add-in sync verify passed (`VERIFY OK` for `BetterParameters.py` and `palette.html`).
