"""Package the built Tauri host and frozen sidecar as a Windows portable candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".build" / "release"
HOST = ROOT / "desktop" / "src-tauri" / "target" / "release" / "fahmm-desktop.exe"
SIDECAR = ROOT / "desktop" / "src-tauri" / "binaries" / "fahmm-sidecar-x86_64-pc-windows-msvc.exe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def dependency_versions() -> dict[str, str]:
    npm = json.loads((ROOT / "desktop" / "package-lock.json").read_text(encoding="utf-8"))
    npm_packages = npm["packages"]
    cargo = tomllib.loads(
        (ROOT / "desktop" / "src-tauri" / "Cargo.lock").read_text(encoding="utf-8")
    )
    uv = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    cargo_packages = {item["name"]: item["version"] for item in cargo["package"]}
    uv_packages = {item["name"]: item["version"] for item in uv["package"]}
    result = {
        f"npm:{name}": npm_packages[f"node_modules/{name}"]["version"]
        for name in ("@tauri-apps/cli", "react", "vite", "vitest")
    }
    result.update(
        {f"cargo:{name}": cargo_packages[name] for name in ("tauri", "tauri-plugin-dialog")}
    )
    result.update(
        {
            f"python:{name}": uv_packages[name]
            for name in ("av", "ctranslate2", "faster-whisper", "numpy", "pyinstaller", "soundcard")
        }
    )
    return result


def package(*, allow_dirty: bool = False) -> Path:
    for binary in (HOST, SIDECAR):
        if not binary.is_file():
            raise FileNotFoundError(f"Build required binary first: {binary}")
    dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
    if dirty and not allow_dirty:
        raise RuntimeError(
            "Source tree is dirty; commit and rebuild or pass --allow-dirty for an internal test candidate"
        )

    version = json.loads(
        (ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
        raise ValueError("Unsafe package version")
    BUILD.mkdir(parents=True, exist_ok=True)
    name = f"fahmm-tauri-{version}-windows-x64-portable"
    staging = BUILD / name
    if staging.resolve().parent != BUILD.resolve():
        raise ValueError("Staging path escaped the release directory")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        files = {"fahmm-desktop.exe": HOST, "fahmm-sidecar.exe": SIDECAR}
        for output_name, source in files.items():
            shutil.copy2(source, staging / output_name)
        manifest = {
            "product": "fahmm Tauri portable candidate",
            "version": version,
            "sourceRevision": git("rev-parse", "HEAD"),
            "sourceDirty": dirty,
            "buildCommands": [
                "uv run --locked python scripts/build_sidecar.py",
                "cd desktop; npm run tauri build -- --no-bundle",
                "uv run --locked python scripts/package_tauri_portable.py",
            ],
            "dependencyVersions": dependency_versions(),
            "filesSha256": {name: sha256(staging / name) for name in files},
        }
        (staging / "BUILD_INFO.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (staging / "README.txt").write_text(
            "Internal release candidate only; v1 acceptance is pending.\n"
            "Extract the folder and run fahmm-desktop.exe on Windows 10/11 x64.\n"
            "Keep fahmm-sidecar.exe beside the host. Models and meeting data are\n"
            "stored in %LOCALAPPDATA%\\fahmm and are not included in this ZIP.\n"
            "See BUILD_INFO.json for source revision and file checksums.\n",
            encoding="utf-8",
        )
        archive = BUILD / f"{name}.zip"
        with zipfile.ZipFile(
            archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as output:
            for path in sorted(staging.iterdir()):
                output.write(path, arcname=f"fahmm/{path.name}")
        (BUILD / f"{archive.name}.sha256").write_text(
            f"{sha256(archive)}  {archive.name}\n",
            encoding="ascii",
        )
        return archive
    finally:
        shutil.rmtree(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Produce an internal candidate from uncommitted sources",
    )
    args = parser.parse_args()
    print(package(allow_dirty=args.allow_dirty))
