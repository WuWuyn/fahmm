"""Build and smoke the Windows x64 sidecar used by Tauri externalBin."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "desktop" / "src-tauri" / "binaries"
BUILD = ROOT / ".build"
TRIPLE = "x86_64-pc-windows-msvc"


def build() -> Path:
    if sys.platform != "win32" or sysconfig.get_platform() != "win-amd64":
        raise SystemExit("Build the sidecar on Windows x64")
    BUILD.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    command = [
        "uv",
        "run",
        "--locked",
        "--group",
        "build",
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "fahmm-sidecar",
        "--distpath",
        str(BUILD / "sidecar-dist"),
        "--workpath",
        str(BUILD / "sidecar-work"),
        "--specpath",
        str(BUILD),
        "--add-data",
        f"{ROOT / 'desktop' / 'protocol' / 'contract.json'};desktop/protocol",
        "--exclude-module",
        "PySide6",
    ]
    for package in ("faster_whisper", "av", "ctranslate2", "tokenizers"):
        command.extend(("--collect-all", package))
    command.append(str(ROOT / "scripts" / "fahmm_sidecar.py"))
    log_path = BUILD / "sidecar-build.log"
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    generated = BUILD / "sidecar-dist" / "fahmm-sidecar.exe"
    if not generated.is_file():
        raise RuntimeError("PyInstaller did not produce the sidecar executable")
    destination = OUT / f"fahmm-sidecar-{TRIPLE}.exe"
    shutil.copyfile(generated, destination)
    with tempfile.TemporaryDirectory(prefix="fahmm-sidecar-smoke-") as directory:
        env = {**os.environ, "LOCALAPPDATA": directory}
        subprocess.run([str(destination), "--worker-smoke"], env=env, check=True, timeout=120)
        payload = (
            b'{"v":1,"kind":"request","id":"hello","op":"session.hello","params":{"versions":[1]}}\n'
            b'{"v":1,"kind":"request","id":"health","op":"system.health","params":{}}\n'
        )
        result = subprocess.run(
            [str(destination)], input=payload, capture_output=True, env=env, check=True, timeout=120
        )
        lines = result.stdout.splitlines()
        if len(lines) != 2 or b'"status":"ready"' not in lines[1]:
            raise RuntimeError("Bundled sidecar handshake failed")
    return destination


if __name__ == "__main__":
    print(build())
