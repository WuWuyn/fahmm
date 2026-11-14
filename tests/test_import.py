import os
import subprocess
import sys


def test_import_does_not_capture_write_or_connect(tmp_path):
    script = """
import socket
import sys
from pathlib import Path
def forbidden(*args, **kwargs):
    raise AssertionError('network on import')
socket.socket.connect = forbidden
import fahmm.audio, fahmm.controller, fahmm.storage, legacy.qt.ui, legacy.qt.app
assert 'soundcard' not in sys.modules
assert not (Path(__import__('os').environ['LOCALAPPDATA']) / 'fahmm').exists()
"""
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
