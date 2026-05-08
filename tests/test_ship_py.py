from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import zipfile


def _load_ship_module():
    repo_root = Path(__file__).resolve().parents[1]
    ship_path = repo_root / "scripts" / "ship.py"
    spec = importlib.util.spec_from_file_location("ship_py_module", ship_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ship = _load_ship_module()


def _write_manifest(path: Path, version: str) -> None:
    path.write_text(
        json.dumps({"autodeskProduct": "Fusion360", "type": "addin", "id": "x", "version": version}, indent=2),
        encoding="utf-8",
    )


def test_should_include_exclusions():
    assert ship._should_include(Path("BetterParameters.py"))
    assert not ship._should_include(Path(".git/config"))
    assert not ship._should_include(Path("dev/dev_harness.html"))
    assert not ship._should_include(Path("settings.json"))
    assert not ship._should_include(Path("update_state.json"))
    assert not ship._should_include(Path("_pending_update/state.txt"))


def test_canonical_arcname_uses_forward_slashes():
    assert ship._canonical_arcname(Path("subdir") / "palette.html") == "BetterParameters/subdir/palette.html"


def test_validate_release_zip_rejects_bad_entry(tmp_path: Path):
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bad\\entry.txt", "x")
    try:
        ship.validate_release_zip(zip_path, "1.2.3")
        raise AssertionError("Expected ShipError for invalid entry path")
    except ship.ShipError:
        pass


def test_build_deterministic_package_shapes_zip_and_version(tmp_path: Path):
    workspace_root = tmp_path
    source_root = tmp_path / "BetterParameters"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "BetterParameters.py").write_text("print('ok')\n", encoding="utf-8")
    (source_root / "palette.html").write_text("<html></html>\n", encoding="utf-8")
    _write_manifest(source_root / "BetterParameters.manifest", "0.1.0")

    # Must be excluded from package.
    (source_root / "settings.json").write_text("{}", encoding="utf-8")
    (source_root / "_pending_update").mkdir(exist_ok=True)
    (source_root / "_pending_update" / "state.json").write_text("{}", encoding="utf-8")

    zip_path = ship.build_deterministic_package(
        source_root=source_root,
        workspace_root=workspace_root,
        expected_version="0.1.1",
    )
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
        assert "BetterParameters/BetterParameters.py" in names
        assert "BetterParameters/palette.html" in names
        assert "BetterParameters/BetterParameters.manifest" in names
        assert "BetterParameters/settings.json" not in names
        assert "BetterParameters/_pending_update/state.json" not in names

        manifest = archive.read("BetterParameters/BetterParameters.manifest").decode("utf-8")
        assert '"version": "0.1.1"' in manifest


def test_write_manifest_version_is_idempotent_when_version_matches(tmp_path: Path):
    manifest_path = tmp_path / "BetterParameters.manifest"
    original = '{\n  "version": "0.8.10"\n}\n'
    manifest_path.write_text(original, encoding="utf-8")

    ship._write_manifest_version(manifest_path, "0.8.10")

    assert manifest_path.read_text(encoding="utf-8") == original


def test_parse_args_supports_reship_in_place_tag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["ship.py", "--reship-in-place-tag", "v0.8.10", "--fusion-tested"])
    args = ship._parse_args()
    assert args.reship_in_place_tag == "v0.8.10"


def test_main_requires_exactly_one_mode_with_reship(monkeypatch, tmp_path: Path):
    workspace_root = tmp_path
    source_root = workspace_root / "BetterParameters"
    source_root.mkdir(parents=True, exist_ok=True)
    _write_manifest(source_root / "BetterParameters.manifest", "0.8.10")

    monkeypatch.setattr("sys.argv", [
        "ship.py",
        "--workspace-root", str(workspace_root),
        "--source-root", str(source_root),
        "--fusion-tested",
        "--reship-in-place-tag", "v0.8.10",
        "--bump-type", "patch",
    ])
    try:
        ship.main()
        raise AssertionError("Expected ShipError for multi-mode selection.")
    except ship.ShipError as exc:
        assert re.search(r"Choose exactly one mode", str(exc))
