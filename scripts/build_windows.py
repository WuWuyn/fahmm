"""Build a checked, versioned Windows x64 portable release candidate."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".build"
RELEASE = ROOT / "release"
FORBIDDEN_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".pcm"}
FORBIDDEN_NAMES = {"model.bin", "metadata.json", "content.json", "original.json", "working.json"}
FORBIDDEN_DIRS = {"meetings", "recordings", "exports", "acceptance"}
SECRET_PATTERN = re.compile(rb"(?:sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,})")


def _run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def _build_env() -> dict[str, str]:
    """Keep unrelated developer tools' DLLs out of the frozen app."""
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required for a locked build")
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        [
            str(Path(sys.executable).parent),
            str(Path(uv).parent),
            str(windows / "System32"),
            str(windows),
            str(windows / "System32" / "Wbem"),
        ]
    )
    return env


def scan_package(folder: Path) -> list[str]:
    """Reject meeting content, model weights, and recognizable access tokens."""
    problems = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(folder)
        parts = {part.lower() for part in relative.parts[:-1]}
        if (
            parts & FORBIDDEN_DIRS
            or path.suffix.lower() in FORBIDDEN_SUFFIXES
            or path.name.lower() in FORBIDDEN_NAMES
        ):
            problems.append(f"User/model content: {relative}")
        if path.stat().st_size <= 10_000_000:
            try:
                if SECRET_PATTERN.search(path.read_bytes()):
                    problems.append(f"Possible secret: {relative}")
            except OSError as exc:
                problems.append(f"Cannot scan {relative}: {exc}")
    return problems


def write_license_inventory(folder: Path, locked: str) -> None:
    """Copy wheel-provided legal files and record any missing notices for review."""
    inventory = []
    licenses = folder / "LICENSES"
    for line in locked.splitlines():
        if not line or line.lstrip().startswith("#") or line[0].isspace():
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        dist = importlib.metadata.distribution(requirement.name)
        copied = []
        for item in dist.files or []:
            name = Path(str(item)).name
            if not re.match(r"(?i)^(license|licence|copying|notice)([._-]|$)", name):
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file():
                continue
            destination = licenses / dist.metadata["Name"] / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied.append(destination.relative_to(folder).as_posix())
        inventory.append(
            {
                "package": dist.metadata["Name"],
                "version": dist.version,
                "license_metadata": dist.metadata.get("License-Expression")
                or (dist.metadata.get("License") or "unspecified").splitlines()[0],
                "wheel_notices": sorted(set(copied)),
            }
        )
    (folder / "LICENSE_INVENTORY.json").write_text(
        json.dumps(sorted(inventory, key=lambda x: x["package"].lower()), indent=2) + "\n",
        encoding="utf-8",
    )


def build() -> Path:
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("A Windows x64 host is required")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    for required in (ROOT / "docs" / "portable.md", ROOT / "docs" / "third-party-notices.md"):
        if not required.is_file():
            raise SystemExit(f"Required release document is missing: {required}")
    BUILD.mkdir(exist_ok=True)
    RELEASE.mkdir(exist_ok=True)
    dist = BUILD / "release-dist"
    cmd = [
        "uv",
        "run",
        "--locked",
        "--extra",
        "legacy-qt",
        "--group",
        "build",
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "fahmm",
        "--distpath",
        str(dist),
        "--workpath",
        str(BUILD / "release-work"),
        "--specpath",
        str(BUILD),
    ]
    for package in ("faster_whisper", "av", "ctranslate2", "tokenizers"):
        cmd += ["--collect-all", package]
    cmd.append(str(ROOT / "scripts" / "fahmm_portable.py"))
    with (BUILD / "release-build.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            cmd, cwd=ROOT, env=_build_env(), stdout=log, stderr=subprocess.STDOUT, check=True
        )
    folder = dist / "fahmm"
    if not (folder / "fahmm.exe").is_file():
        raise RuntimeError("PyInstaller did not produce fahmm.exe")
    if (folder / "_internal" / "icuuc.dll").exists():
        raise RuntimeError("A non-system ICU DLL leaked into the build")
    subprocess.run(
        [str(folder / "fahmm.exe"), "--worker-smoke"],
        env=_build_env(),
        cwd=folder,
        check=True,
        timeout=60,
    )
    smoke_env = _build_env()
    smoke_env["QT_QPA_PLATFORM"] = "offscreen"
    subprocess.run(
        [str(folder / "fahmm.exe"), "--smoke"], env=smoke_env, cwd=folder, check=True, timeout=60
    )
    for source, name in (
        (ROOT / "README.md", "README.md"),
        (ROOT / "LICENSE", "LICENSE"),
        (ROOT / "docs" / "portable.md", "PORTABLE.md"),
        (ROOT / "docs" / "third-party-notices.md", "THIRD_PARTY_NOTICES.md"),
    ):
        (folder / name).write_bytes(source.read_bytes())
    locked = _run(
        "uv",
        "export",
        "--locked",
        "--extra",
        "legacy-qt",
        "--no-dev",
        "--no-hashes",
        "--no-emit-project",
    )
    (folder / "RUNTIME_DEPENDENCIES.txt").write_text(locked + "\n", encoding="utf-8")
    write_license_inventory(folder, locked)
    info = {
        "product": "fahmm",
        "version": version,
        "source_commit": _run("git", "rev-parse", "HEAD"),
        "source_dirty": bool(_run("git", "status", "--porcelain")),
        "build_os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "pyinstaller": _run(
            "uv", "run", "--locked", "--group", "build", "pyinstaller", "--version"
        ),
        "model_weights_bundled": False,
    }
    (folder / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    problems = scan_package(folder)
    if problems:
        raise RuntimeError("Package content scan failed:\n" + "\n".join(problems))

    archive = RELEASE / f"fahmm-{version}-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                relative = Path("fahmm") / path.relative_to(folder)
                output.write(path, relative.as_posix())
    with archive.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
        names = set(check.namelist())
        if "fahmm/fahmm.exe" not in names or "fahmm/THIRD_PARTY_NOTICES.md" not in names:
            raise RuntimeError("Archive is missing its executable or notices")
        inventory = json.loads(check.read("fahmm/LICENSE_INVENTORY.json"))
        if any(
            "fahmm/" + notice not in names
            for entry in inventory
            for notice in entry["wheel_notices"]
        ):
            raise RuntimeError("Archive notice inventory does not match its contents")
    with archive.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != digest:
            raise RuntimeError("Archive hash changed after writing")
    return archive


if __name__ == "__main__":
    print(build())
