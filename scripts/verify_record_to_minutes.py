"""Exercise the local meeting workflow with simulated audio devices and a real ASR model.

All recordings, model copies, transcripts and exports are written to a new
caller-selected directory. This does not access physical microphones or send
meeting content to a provider.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import shutil
import threading
import time
import wave
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import psutil
from docx import Document

from fahmm.audio import AudioDevice
from fahmm.bridge.protocol import encode_frame, validate_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.media import iter_pcm

RATE = 48_000


class ReplayStream:
    def __init__(self, audio: np.ndarray, ended: threading.Event, gain: float) -> None:
        self.audio, self.ended, self.gain = audio, ended, gain
        self.position = 0

    def read(self, frames: int) -> np.ndarray:
        time.sleep(frames / RATE)
        first = self.position
        last = min(len(self.audio), first + frames)
        self.position = last
        data = self.audio[first:last] * self.gain
        if last >= len(self.audio):
            self.ended.set()
        return np.pad(data, (0, frames - len(data))).astype(np.float32)


class ReplayCapture:
    def __init__(self, audio: np.ndarray) -> None:
        self.audio = audio
        self.ended = {source: threading.Event() for source in ("system", "microphone")}

    def list_devices(self) -> dict:
        return {
            "system": [AudioDevice("test-system", "Synthetic system audio")],
            "microphone": [AudioDevice("test-mic", "Synthetic microphone")],
        }

    @contextmanager
    def open(self, source: str, _device_id: str):
        yield ReplayStream(self.audio, self.ended[source], 0.35 if source == "system" else 0.7)


def call(app: BridgeApplication, operation: str, **params) -> dict:
    request = {"v": 1, "kind": "request", "id": "flow-test", "op": operation, "params": params}
    response = app.handle(validate_frame(encode_frame(request)))
    response = validate_frame(encode_frame(response))
    if response["kind"] != "response":
        raise RuntimeError(f"{operation} failed: {response['error']['code']}")
    return response["result"]


def wait_for(predicate, *, seconds: float, description: str) -> object:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        if psutil.virtual_memory().available < 1024**3:
            raise MemoryError("Stopping the synthetic test because available RAM is below 1 GiB")
        time.sleep(0.2)
    raise TimeoutError(f"Timed out while {description}")


def run(sample: Path, model_id: str, output: Path) -> dict:
    if psutil.virtual_memory().available < 2 * 1024**3:
        raise MemoryError("At least 2 GiB of available RAM is required for this short test")
    user_models = Path(os.environ["LOCALAPPDATA"]) / "fahmm" / "models"
    index = json.loads((user_models / "index.json").read_text(encoding="utf-8"))
    model = index["installations"][model_id]
    source_model = user_models / "installed" / model_id
    if not source_model.is_dir() or not sample.is_file():
        raise FileNotFoundError("The selected model or sample is missing")
    output.mkdir(parents=False, exist_ok=False)
    data_root = output / "data"
    model_root = data_root / "models"
    target_model = model_root / "installed" / model_id
    target_model.mkdir(parents=True)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        shutil.copy2(source_model / name, target_model / name)
    (model_root / "index.json").write_text(
        json.dumps({"schema_version": 1, "selected": model_id, "installations": {model_id: model}}),
        encoding="utf-8",
    )
    audio_bytes = b"".join(chunk.data for chunk in iter_pcm(sample, rate=RATE))
    audio = np.frombuffer(audio_bytes, dtype="<i2").astype(np.float32) / 32768.0
    if len(audio) < RATE or len(audio) > RATE * 30:
        raise ValueError("Use a synthetic audio sample between 1 and 30 seconds")
    capture = ReplayCapture(audio)
    app = BridgeApplication(data_root)
    app.recorder.capture = capture
    call(app, "session.hello", versions=[1])
    meeting = None
    try:
        meeting = call(app, "recording.start", systemId="test-system", microphoneId="test-mic")[
            "meetingId"
        ]
        wait_for(
            lambda: all(event.is_set() for event in capture.ended.values()),
            seconds=len(audio) / RATE + 20,
            description="recording synthetic audio",
        )
        call(app, "recording.stop")

        def recording_done():
            state = call(app, "recording.snapshot")
            if state["state"] == "error":
                raise RuntimeError("Synthetic recording failed")
            return state if state["state"] == "completed" else None

        wait_for(recording_done, seconds=30, description="finalizing the recording")
        recording = app.store._meeting_dir(meeting) / "recording.wav"
        with wave.open(str(recording), "rb") as input_audio:
            channels = np.frombuffer(
                input_audio.readframes(input_audio.getnframes()), dtype="<i2"
            ).reshape(-1, 2)
            if not all(np.max(np.abs(channels[:, i].astype(np.int32))) > 100 for i in (0, 1)):
                raise RuntimeError("Both synthetic audio sources were not preserved")
            recorded_seconds = len(channels) / input_audio.getframerate()
        os.environ.update(
            FAHMM_ASR_DEVICE="cpu", FAHMM_ASR_COMPUTE_TYPE="int8", FAHMM_ASR_BEAM_SIZE="5"
        )
        run_id = call(app, "asr.start", meetingId=meeting, modelId=model_id, language="vi")["runId"]

        def asr_done():
            status = call(app, "asr.status")
            if status["state"] == "error":
                raise RuntimeError(f"ASR failed: {status['errorCode']}")
            return status if status["state"] == "completed" else None

        try:
            status = wait_for(asr_done, seconds=180, description="transcribing")
        except BaseException:
            app.asr.cancel()
            app.asr.wait(10)
            raise
        transcript = call(app, "transcript.read", meetingId=meeting, runId=run_id)["run"]
        if status["segmentCount"] < 1 or not transcript["working"]:
            raise RuntimeError("ASR returned no transcript segments")
        first = call(
            app, "minutes.generateOffline", meetingId=meeting, runId=run_id, meetingType="general"
        )["versionId"]
        version = call(app, "minutes.read", meetingId=meeting, versionId=first)["version"]
        claims = [
            item
            for section in version["content"]["domain"]["sections"].values()
            for item in section
        ]
        if not claims:
            raise RuntimeError("No source-linked minutes were generated")
        marker = "Nội dung kiểm tra đã được chỉnh sửa."
        claims[0]["text"] = marker
        claims[0]["review_status"] = "confirmed"
        edited = call(
            app,
            "minutes.editDomain",
            meetingId=meeting,
            versionId=first,
            content=version["content"],
        )["versionId"]
        listing = call(app, "minutes.list", meetingId=meeting)
        if listing["activeVersionId"] != edited:
            raise RuntimeError("The edited minutes did not become the current document")
        transcript_path, minutes_path, docx_path = (
            output / name for name in ("transcript.txt", "minutes.md", "minutes.docx")
        )
        call(
            app,
            "export.writeTranscript",
            meetingId=meeting,
            runId=run_id,
            nativePath=str(transcript_path.resolve()),
            overwrite=False,
        )
        call(
            app,
            "export.writeMinutes",
            meetingId=meeting,
            versionId=edited,
            nativePath=str(minutes_path.resolve()),
            overwrite=False,
        )
        call(
            app,
            "export.writeMinutesDocx",
            meetingId=meeting,
            versionId=edited,
            nativePath=str(docx_path.resolve()),
            overwrite=False,
        )
        if not transcript_path.read_text(
            encoding="utf-8"
        ).strip() or marker not in minutes_path.read_text(encoding="utf-8"):
            raise RuntimeError("The exported text does not contain the expected data")
        word = Document(docx_path)
        word_text = (
            "\n".join(p.text for p in word.paragraphs)
            + "\n"
            + "\n".join(
                cell.text for table in word.tables for row in table.rows for cell in row.cells
            )
        )
        if marker not in word_text:
            raise RuntimeError("The exported Word file does not contain the saved edit")
        reopened = BridgeApplication(data_root)
        call(reopened, "session.hello", versions=[1])
        if call(reopened, "minutes.list", meetingId=meeting)["activeVersionId"] != edited:
            raise RuntimeError("The current minutes were not retained after reopening")
        report = {
            "recording": "completed",
            "recorded_seconds": round(recorded_seconds, 2),
            "audio_sources": 2,
            "asr": "completed",
            "segments": status["segmentCount"],
            "minutes": "generated_and_edited",
            "active_document": "verified",
            "exports": ["transcript.txt", "minutes.md", "minutes.docx"],
            "privacy": "restricted",
            "physical_devices_tested": False,
        }
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report
    finally:
        if meeting and app.recorder.snapshot().state.value in {"starting", "recording", "paused"}:
            app.recorder.stop()
        app.recorder.wait(15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="A new local test directory")
    args = parser.parse_args()
    if len(args.model_id) != 32 or any(c not in "0123456789abcdef" for c in args.model_id):
        parser.error("Invalid installed model ID")
    print(
        json.dumps(
            run(args.sample.resolve(), args.model_id, args.output.resolve()), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
