"""
update_helper.py — sync BetterParameters source to live Fusion add-in directory.

Usage (basic):
    python update_helper.py SOURCE DEST [skip_name ...] [--verify]

Arguments:
    SOURCE        Source directory (BetterParameters source root)
    DEST          Destination directory (live Fusion add-in root)
    skip_name ... Names to exclude at every level (files or directories)
    --verify      After sync, hash-check BetterParameters.py and palette.html.
                  Exits non-zero if either file is missing or mismatched.

Exit codes:
    0  All copies succeeded (and verify passed, if --verify given)
    1  One or more copy errors, or verify mismatch

Notes:
  - BetterParameters.manifest is intentionally excluded from the canonical sync
    command so the ship-script-bumped version in the live dir is preserved during
    development. The --verify check does NOT include the manifest for this reason.
  - All errors are reported per-file; the sync continues even if individual files
    fail, so the full error set is visible in a single run.
  - `dev/` is always skipped so mock-fixture files are never pushed into the live
    Fusion add-in directory.
"""
import hashlib
import os
import shutil
import sys

ALWAYS_SKIP = {".git", ".gitignore", "dev"}

# Files hash-checked when --verify is given.  Manifest excluded intentionally
# (see module docstring).
VERIFY_FILES = ["BetterParameters.py", "palette.html"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Core sync
# ---------------------------------------------------------------------------

def apply_update(source_dir, target_dir, skip_names=None, _depth=0):
    """Recursively copy source_dir → target_dir, skipping skip_names entries.

    Returns (copied_count, skipped_count, error_count).
    Never raises — all per-file errors are caught, printed, and counted.
    """
    skip_names = set(skip_names or [])
    skip_names.update(ALWAYS_SKIP)

    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as exc:
        print(f"  ERROR cannot create target dir {target_dir}: {exc}", file=sys.stderr)
        return 0, 0, 1

    try:
        entries = os.listdir(source_dir)
    except Exception as exc:
        print(f"  ERROR cannot list source dir {source_dir}: {exc}", file=sys.stderr)
        return 0, 0, 1

    copied = skipped = errors = 0

    for name in sorted(entries):
        source_path = os.path.join(source_dir, name)
        target_path = os.path.join(target_dir, name)

        if name in skip_names:
            print(f"  SKIP  {source_path}")
            skipped += 1
            continue

        if os.path.isdir(source_path):
            c, s, e = apply_update(source_path, target_path, skip_names=skip_names, _depth=_depth + 1)
            copied += c
            skipped += s
            errors += e
        else:
            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source_path, target_path)
                print(f"  COPY  {source_path}")
                copied += 1
            except Exception as exc:
                print(f"  ERROR {source_path}: {exc}", file=sys.stderr)
                errors += 1

    return copied, skipped, errors


# ---------------------------------------------------------------------------
# Post-sync verification
# ---------------------------------------------------------------------------

def verify_sync(source_dir, target_dir, files):
    """Hash-check each file in files between source_dir and target_dir.

    Returns list of file names that are missing from target or mismatched.
    Prints one status line per file.
    """
    mismatches = []
    for name in files:
        src = os.path.join(source_dir, name)
        dst = os.path.join(target_dir, name)

        if not os.path.exists(src):
            print(f"  VERIFY SKIP   {name} (not present in source)")
            continue

        if not os.path.exists(dst):
            print(f"  VERIFY MISS   {name} (missing from target)", file=sys.stderr)
            mismatches.append(name)
            continue

        try:
            src_hash = _file_sha256(src)
            dst_hash = _file_sha256(dst)
        except Exception as exc:
            print(f"  VERIFY ERROR  {name}: {exc}", file=sys.stderr)
            mismatches.append(name)
            continue

        if src_hash == dst_hash:
            print(f"  VERIFY OK     {name}  ({src_hash[:16]})")
        else:
            print(
                f"  VERIFY FAIL   {name}\n"
                f"                src {src_hash[:16]}\n"
                f"                dst {dst_hash[:16]}",
                file=sys.stderr,
            )
            mismatches.append(name)

    return mismatches


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    raw_args = sys.argv[1:]

    verify = "--verify" in raw_args
    positional = [a for a in raw_args if a != "--verify"]

    if len(positional) < 2:
        print(
            "Usage: update_helper.py SOURCE DEST [skip_name ...] [--verify]",
            file=sys.stderr,
        )
        sys.exit(1)

    source_dir = positional[0]
    target_dir = positional[1]
    skip_names = set(positional[2:])

    print(f"Sync  {source_dir}")
    print(f"  ->  {target_dir}")
    if skip_names:
        print(f"Skip  {', '.join(sorted(skip_names))}")
    print()

    copied, skipped, errors = apply_update(source_dir, target_dir, skip_names=skip_names)

    print(f"\nDone: {copied} copied, {skipped} skipped, {errors} error(s).")

    verify_errors = 0
    if verify:
        print("\nVerify:")
        mismatches = verify_sync(source_dir, target_dir, VERIFY_FILES)
        verify_errors = len(mismatches)
        if mismatches:
            print(f"\nVerify FAILED: {', '.join(mismatches)}", file=sys.stderr)

    sys.exit(1 if (errors > 0 or verify_errors > 0) else 0)
