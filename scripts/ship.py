#!/usr/bin/env python3
"""Cross-platform BetterParameters shipping script.

Canonical shipping entrypoint for Windows and macOS.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile


CORE_VERIFY_FILES = ("BetterParameters.py", "palette.html")
EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "dev",
    "_pending_update",
    "_release_stage",
    "_releases_packages",
    ".release_stage",
}
EXCLUDED_FILE_NAMES = {
    "settings.json",
    "update_state.json",
    ".gitignore",
}
RELEASE_NOTES_TEMPLATE_FALLBACK = "BetterParameters v{{VERSION}}\n\nHighlights:\n{{AUTO_HIGHLIGHTS}}\n"


class ShipError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise ShipError(
            "Command failed:\n"
            + " ".join(cmd)
            + f"\nexit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def _tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _require_tool(name: str) -> None:
    if not _tool_exists(name):
        raise ShipError(f"Required tool not found on PATH: {name}")


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_manifest_version(manifest_path: Path) -> str:
    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    version = str(data.get("version", "")).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ShipError(f"Manifest version is missing/invalid in {manifest_path}")
    return version


def _write_manifest_version(manifest_path: Path, version: str) -> None:
    raw = manifest_path.read_text(encoding="utf-8-sig")
    replaced = re.sub(r'"version"\s*:\s*"\d+\.\d+\.\d+"', f'"version": "{version}"', raw, count=1)
    if replaced == raw:
        raise ShipError("Failed to update manifest version.")
    manifest_path.write_text(replaced, encoding="utf-8", newline="\n")


def _bumped_version(current: str, mode: str) -> str:
    major, minor, patch = [int(part) for part in current.split(".")]
    if mode == "major":
        return f"{major + 1}.0.0"
    if mode == "feature":
        return f"{major}.{minor + 1}.0"
    if mode == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ShipError(f"Unsupported bump type: {mode}")


def _semver_from_tag(tag: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ShipError(f"Expected tag format vX.Y.Z, received: {tag}")
    return tag[1:]


def _is_hidden_path(relative_path: Path) -> bool:
    return any(part.startswith(".") for part in relative_path.parts if part not in (".", ".."))


def _should_include(relative_path: Path) -> bool:
    if not relative_path.parts:
        return False
    if _is_hidden_path(relative_path):
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in relative_path.parts):
        return False
    if relative_path.name in EXCLUDED_FILE_NAMES:
        return False
    return True


def _canonical_arcname(relative_path: Path) -> str:
    rel_posix = PurePosixPath(*relative_path.parts).as_posix()
    return f"BetterParameters/{rel_posix}"


def validate_entry_name(name: str) -> None:
    if "\\" in name:
        raise ShipError(f"Invalid zip entry contains backslash: {name}")
    if name.startswith("/") or (len(name) >= 3 and name[1:3] == ":/"):
        raise ShipError(f"Invalid zip entry absolute path: {name}")
    parts = [part for part in name.split("/") if part]
    if any(part == ".." for part in parts):
        raise ShipError(f"Invalid zip entry path traversal: {name}")


def validate_release_zip(zip_path: Path, expected_version: str, allowed_top_level_entries: set[str] | None = None) -> None:
    allowed_top_level_entries = allowed_top_level_entries or set()
    with zipfile.ZipFile(zip_path, "r") as archive:
        manifest_found = False
        for info in archive.infolist():
            validate_entry_name(info.filename)
            normalized = info.filename.replace("\\", "/").rstrip("/")
            if not normalized:
                continue
            if normalized == "BetterParameters/BetterParameters.manifest":
                manifest_found = True
            if normalized.startswith("BetterParameters/"):
                continue
            if normalized in allowed_top_level_entries:
                continue
            raise ShipError(f"Unexpected top-level zip entry: {normalized}")
        if not manifest_found:
            raise ShipError("Zip missing BetterParameters/BetterParameters.manifest")
        manifest_raw = archive.read("BetterParameters/BetterParameters.manifest").decode("utf-8-sig")
        if not re.search(r'"version"\s*:\s*"' + re.escape(expected_version) + r'"', manifest_raw):
            raise ShipError(f"Zip manifest version mismatch. Expected {expected_version}")


def _copy_source_to_stage(source_root: Path, stage_pkg_root: Path) -> None:
    if stage_pkg_root.exists():
        shutil.rmtree(stage_pkg_root)
    stage_pkg_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_root.rglob("*")):
        rel = path.relative_to(source_root)
        if not _should_include(rel):
            continue
        target = stage_pkg_root / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def build_deterministic_package(
    source_root: Path,
    workspace_root: Path,
    expected_version: str,
    release_assets_path: Path | None = None,
) -> Path:
    stage_root = workspace_root / "_release_stage"
    stage_pkg_root = stage_root / "BetterParameters"
    zip_root = workspace_root / "_releases_packages"
    zip_path = zip_root / f"BetterParameters-{expected_version}.zip"

    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    zip_root.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    _copy_source_to_stage(source_root, stage_pkg_root)
    _write_manifest_version(stage_pkg_root / "BetterParameters.manifest", expected_version)

    allowed = set()
    if release_assets_path and release_assets_path.exists():
        for asset in sorted(release_assets_path.iterdir()):
            if not asset.is_file():
                continue
            shutil.copy2(asset, stage_root / asset.name)
            allowed.add(asset.name)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(stage_root)
            if rel.parts and rel.parts[0] == "BetterParameters":
                archive.write(path, arcname=_canonical_arcname(Path(*rel.parts[1:])))
            else:
                archive.write(path, arcname=PurePosixPath(*rel.parts).as_posix())

    validate_release_zip(zip_path, expected_version, allowed_top_level_entries=allowed)
    return zip_path


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sync_source_to_live(workspace_root: Path, source_root: Path, live_addin_root: Path) -> None:
    update_helper = source_root / "update_helper.py"
    if not update_helper.exists():
        raise ShipError(f"update_helper.py missing: {update_helper}")
    cmd = [
        sys.executable,
        str(update_helper),
        str(source_root),
        str(live_addin_root),
        "settings.json",
        "update_state.json",
        "_pending_update",
        ".git",
        "BetterParameters.manifest",
    ]
    _run(cmd, cwd=workspace_root)
    for filename in CORE_VERIFY_FILES:
        src = source_root / filename
        dst = live_addin_root / filename
        if not dst.exists():
            raise ShipError(f"Live sync verification missing file: {dst}")
        if _sha256(src) != _sha256(dst):
            raise ShipError(f"Live sync hash mismatch: {filename}")


def _gh_release_exists(repo_slug: str, tag: str) -> bool:
    proc = _run(["gh", "release", "view", tag, "--repo", repo_slug], check=False)
    return proc.returncode == 0


def _git_branch(repo_root: Path) -> str:
    return _run(["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def _local_tag_exists(repo_root: Path, tag: str) -> bool:
    out = _run(["git", "-C", str(repo_root), "tag", "-l", tag]).stdout.strip()
    return bool(out)


def _remote_tag_exists(repo_root: Path, tag: str) -> bool:
    proc = _run(
        ["git", "-C", str(repo_root), "ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
        check=False,
    )
    return bool(proc.stdout.strip())


def _assert_clean_worktree(repo_root: Path) -> None:
    out = _run(["git", "-C", str(repo_root), "status", "--porcelain"]).stdout.strip()
    if out:
        raise ShipError("Working tree must be clean before shipping.")


def _previous_version_tag(repo_root: Path, current_tag: str) -> str:
    tags = _run(["git", "-C", str(repo_root), "tag", "--list", "v*", "--sort=v:refname"]).stdout.splitlines()
    if not tags:
        return ""
    if current_tag in tags:
        idx = tags.index(current_tag)
        if idx > 0:
            return tags[idx - 1]
    return ""


def _auto_release_highlights(repo_root: Path, current_tag: str) -> list[str]:
    prev = _previous_version_tag(repo_root, current_tag)
    if not prev:
        return ["- Initial release."]
    subjects = _run(["git", "-C", str(repo_root), "log", "--pretty=format:%s", f"{prev}..HEAD"]).stdout.splitlines()
    meaningful = []
    for line in subjects:
        text = line.strip()
        if not text or re.match(r"^Release v\d+\.\d+\.\d+$", text):
            continue
        if text not in meaningful:
            meaningful.append(text)
    if meaningful:
        return [f"- {s}" for s in meaningful]
    short_stat = _run(["git", "-C", str(repo_root), "diff", "--shortstat", f"{prev}..HEAD"]).stdout.strip()
    changed_files = [
        x.strip()
        for x in _run(["git", "-C", str(repo_root), "diff", "--name-only", f"{prev}..HEAD"]).stdout.splitlines()
        if x.strip()
    ]
    highlights: list[str] = []
    if short_stat:
        highlights.append(f"- {short_stat}")
    if changed_files:
        top = changed_files[:6]
        line = "- Updated files: " + ", ".join(top)
        if len(changed_files) > len(top):
            line += f", +{len(changed_files) - len(top)} more"
        highlights.append(line)
    return highlights or ["- Internal maintenance changes."]


def _is_low_signal_highlights(highlights: list[str]) -> bool:
    if not highlights:
        return True
    pattern = re.compile(r"^- (Initial release\.|Internal maintenance changes\.|\d+ files changed, .*|Updated files: .*)$")
    meaningful = [h for h in highlights if h.strip() and not pattern.match(h.strip())]
    return len(meaningful) == 0


def _release_notes_file(
    repo_root: Path,
    tag: str,
    version: str,
    provided_notes_file: str,
) -> Path:
    notes_file = Path(provided_notes_file).resolve() if provided_notes_file else None
    pending = repo_root / "scripts" / "release_notes_pending.md"
    if not notes_file and pending.exists():
        notes_file = pending
    temp = Path(tempfile.gettempdir()) / f"bp_release_notes_{version}.md"
    if notes_file:
        if not notes_file.exists():
            raise ShipError(f"Notes file not found: {notes_file}")
        temp.write_text(notes_file.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        return temp
    highlights = _auto_release_highlights(repo_root, tag)
    if _is_low_signal_highlights(highlights):
        raise ShipError(
            f"Auto-generated release notes are low-signal for {tag}. "
            "Provide --notes-file with curated notes."
        )
    template_path = repo_root / "scripts" / "release_notes_template.md"
    template_text = template_path.read_text(encoding="utf-8") if template_path.exists() else RELEASE_NOTES_TEMPLATE_FALLBACK
    body = template_text.replace("{{VERSION}}", version)
    if "{{AUTO_HIGHLIGHTS}}" in body:
        body = body.replace("{{AUTO_HIGHLIGHTS}}", "\n".join(highlights))
    elif re.search(r"<feature 1>|<feature 2>|<fixes/perf notes>|<item 1>|<item 2>", body):
        body = f"BetterParameters v{version}\n\nHighlights:\n" + "\n".join(highlights)
    elif not re.search(r"(?im)^\s*Highlights:\s*$", body):
        body = body.rstrip() + "\n\nHighlights:\n" + "\n".join(highlights)
    temp.write_text(body, encoding="utf-8", newline="\n")
    return temp


def _release_json(repo_slug: str, tag: str) -> dict:
    out = _run(["gh", "release", "view", tag, "--repo", repo_slug, "--json", "tagName,url,assets"]).stdout
    return json.loads(out)


def _write_report(workspace_root: Path, report: dict) -> Path:
    report_dir = workspace_root / "scripts" / "_ship_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"ship_{run_id}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8", newline="\n")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform BetterParameters ship script.")
    parser.add_argument("--bump-type", choices=("major", "feature", "patch"), default="")
    parser.add_argument("--finalize-existing-tag", default="")
    parser.add_argument("--workspace-root", default="")
    parser.add_argument("--source-root", default="")
    parser.add_argument("--live-addin-root", default="")
    parser.add_argument("--repo-slug", default="macifoxispurple/FusionBetterParameters")
    parser.add_argument("--notes-file", default="")
    parser.add_argument("--fusion-tested", action="store_true")
    parser.add_argument("--skip-push", action="store_true")
    parser.add_argument("--skip-release", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.fusion_tested:
        raise ShipError("Missing --fusion-tested.")
    finalize_mode = bool(args.finalize_existing_tag)
    if finalize_mode and args.bump_type:
        raise ShipError("Use either --bump-type or --finalize-existing-tag, not both.")
    if not finalize_mode and not args.bump_type:
        raise ShipError("Provide --bump-type or --finalize-existing-tag.")

    _require_tool("git")
    _require_tool("python")
    if not args.skip_release:
        _require_tool("gh")

    workspace_root = Path(args.workspace_root).resolve() if args.workspace_root else _repo_root_from_script()
    source_root = Path(args.source_root).resolve() if args.source_root else (workspace_root / "BetterParameters")
    live_addin_root_raw = args.live_addin_root or os.environ.get("BP_LIVE_ADDIN_ROOT", "")
    live_addin_root = Path(live_addin_root_raw).resolve() if live_addin_root_raw else None
    manifest_path = source_root / "BetterParameters.manifest"
    if not workspace_root.exists():
        raise ShipError(f"Workspace root missing: {workspace_root}")
    if not source_root.exists():
        raise ShipError(f"Source root missing: {source_root}")
    if not manifest_path.exists():
        raise ShipError(f"Manifest missing: {manifest_path}")

    _assert_clean_worktree(workspace_root)
    if not args.skip_release:
        _run(["gh", "auth", "status", "--hostname", "github.com"])

    branch = _git_branch(workspace_root)
    current_version = _parse_manifest_version(manifest_path)

    if finalize_mode:
        tag = args.finalize_existing_tag.strip()
        new_version = _semver_from_tag(tag)
        if not args.skip_push and not _remote_tag_exists(workspace_root, tag):
            raise ShipError(f"Finalize target tag not found on remote: {tag}")
    else:
        new_version = _bumped_version(current_version, args.bump_type)
        tag = f"v{new_version}"
        if _local_tag_exists(workspace_root, tag):
            raise ShipError(f"Local tag already exists: {tag}")
        if not args.skip_push and _remote_tag_exists(workspace_root, tag):
            raise ShipError(f"Remote tag already exists: {tag}")

    notes_temp = _release_notes_file(workspace_root, tag, new_version, args.notes_file)
    report = {
        "mode": "finalize" if finalize_mode else "normal",
        "branch": branch,
        "tag": tag,
        "version": new_version,
        "release_url": "",
        "steps": [],
    }

    try:
        if not finalize_mode:
            if live_addin_root:
                if not live_addin_root.exists():
                    raise ShipError(f"Live add-in root missing: {live_addin_root}")
                _sync_source_to_live(workspace_root, source_root, live_addin_root)
                report["steps"].append("sync_source_to_live:ok")
            else:
                report["steps"].append("sync_source_to_live:skipped")

            zip_path = build_deterministic_package(
                source_root=source_root,
                workspace_root=workspace_root,
                expected_version=new_version,
                release_assets_path=workspace_root / "scripts" / "release_assets",
            )
            report["steps"].append(f"package_build_verify:ok:{zip_path}")

            _write_manifest_version(manifest_path, new_version)
            _run(["git", "-C", str(workspace_root), "add", "-A"])
            diff = _run(["git", "-C", str(workspace_root), "diff", "--cached", "--quiet"], check=False)
            if diff.returncode == 0:
                raise ShipError("No staged changes to commit.")
            _run(["git", "-C", str(workspace_root), "commit", "-m", f"Release {tag}"])
            _run(["git", "-C", str(workspace_root), "tag", "-a", tag, "-m", f"Release {tag}"])
            report["steps"].append("commit_and_tag:ok")

            if not args.skip_push:
                _run(["git", "-C", str(workspace_root), "push", "origin", branch])
                _run(["git", "-C", str(workspace_root), "push", "origin", tag])
                report["steps"].append("push:ok")
        else:
            zip_path = workspace_root / "_releases_packages" / f"BetterParameters-{new_version}.zip"
            allowed = set()
            release_assets_path = workspace_root / "scripts" / "release_assets"
            if release_assets_path.exists():
                allowed = {p.name for p in release_assets_path.iterdir() if p.is_file()}
            validate_release_zip(zip_path, new_version, allowed_top_level_entries=allowed)
            report["steps"].append("finalize_package_verify:ok")

        if not args.skip_release:
            if _gh_release_exists(args.repo_slug, tag):
                _run(["gh", "release", "edit", tag, "--repo", args.repo_slug, "--title", tag, "--notes-file", str(notes_temp)])
                _run(["gh", "release", "upload", tag, str(zip_path), "--repo", args.repo_slug, "--clobber"])
            else:
                _run(["gh", "release", "create", tag, str(zip_path), "--repo", args.repo_slug, "--title", tag, "--notes-file", str(notes_temp)])
            release = _release_json(args.repo_slug, tag)
            if release.get("tagName") != tag:
                raise ShipError(f"Release tag mismatch: expected {tag}, got {release.get('tagName')}")
            asset_names = [a.get("name", "") for a in release.get("assets", [])]
            expected_asset = f"BetterParameters-{new_version}.zip"
            if expected_asset not in asset_names:
                raise ShipError(f"Release asset missing expected zip: {expected_asset}")
            report["release_url"] = release.get("url", "")
            report["steps"].append("release_publish_verify:ok")
        else:
            report["steps"].append("release_publish_verify:skipped")

    finally:
        if notes_temp.exists():
            notes_temp.unlink()

    report_path = _write_report(workspace_root, report)
    print(f"Shipped {tag} successfully.")
    print(f"Report: {report_path}")
    if report["release_url"]:
        print(f"Release URL: {report['release_url']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ShipError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
