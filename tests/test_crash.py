import subprocess
import sys
import time
import wave

from fahmm.storage import MeetingStore


def test_killed_process_recovers_flushed_audio_without_touching_other_meeting(tmp_path):
    store = MeetingStore(tmp_path)
    other = store.create({"system": "speaker", "microphone": "mic"})
    script = """
import sys
import time
from pathlib import Path
sys.path.insert(0, 'tests')
from test_controller import FakeCapture
from fahmm.controller import SessionController
from fahmm.storage import MeetingStore
controller = SessionController(FakeCapture(), MeetingStore(Path(sys.argv[1])))
print(controller.start('speaker', 'mic'), flush=True)
time.sleep(30)
"""
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        meeting = process.stdout.readline().strip()
        assert len(meeting) == 32
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if list((tmp_path / meeting / "system").glob("*.wav")) and list(
                (tmp_path / meeting / "microphone").glob("*.wav")
            ):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("No flushed chunks before kill")
        process.kill()
        process.wait(timeout=5)
        assert meeting in [item["id"] for item in store.incomplete()]
        result = store.finalize(meeting)
        with wave.open(str(result.path), "rb") as file:
            assert file.getnchannels() == 2
            assert file.getnframes() > 0
        assert store.metadata(other)["state"] == "recording"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
