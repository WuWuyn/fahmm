"""Non-blocking Qt audio output fed by the same local decoder used for imports."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from fahmm.media import iter_pcm


class AudioPlayer(QObject):
    error = Signal(str)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._feed)
        self._sink: QAudioSink | None = None
        self._device = None
        self._stop = threading.Event()
        self._queue: queue.Queue[bytes | Exception | None] = queue.Queue(maxsize=8)
        self._pending = b""
        self._eof = False

    def play(self, path: Path, start_seconds: float = 0.0) -> None:
        self.stop()
        output = QMediaDevices.defaultAudioOutput()
        if output.isNull():
            raise RuntimeError("No audio output device is available")
        audio_format = QAudioFormat()
        audio_format.setSampleRate(48_000)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not output.isFormatSupported(audio_format):
            raise RuntimeError("The audio output does not support 48 kHz mono PCM")
        self._sink = QAudioSink(output, audio_format, self)
        self._sink.setBufferSize(48_000)
        self._device = self._sink.start()
        if self._device is None:
            self.stop()
            raise RuntimeError("Could not start audio playback")
        self._stop = threading.Event()
        self._queue = queue.Queue(maxsize=8)
        self._pending = b""
        self._eof = False
        thread = threading.Thread(
            target=self._decode, args=(Path(path), start_seconds, self._stop, self._queue),
            daemon=True,
        )
        thread.start()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._stop.set()
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        self._sink = None
        self._device = None
        self._pending = b""

    @staticmethod
    def _decode(
        path: Path,
        start_seconds: float,
        stopped: threading.Event,
        output: queue.Queue[bytes | Exception | None],
    ) -> None:
        try:
            for chunk in iter_pcm(path, start_seconds):
                if stopped.is_set():
                    return
                while not stopped.is_set():
                    try:
                        output.put(chunk.data, timeout=0.1)
                        break
                    except queue.Full:
                        pass
        except Exception as exc:
            if not stopped.is_set():
                output.put(exc)
        finally:
            while not stopped.is_set():
                try:
                    output.put(None, timeout=0.1)
                    break
                except queue.Full:
                    pass

    def _feed(self) -> None:
        if self._sink is None or self._device is None:
            return
        if not self._pending:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                item = b""
            if isinstance(item, Exception):
                self.stop()
                self.error.emit(str(item))
                return
            if item is None:
                self._eof = True
            else:
                self._pending = item
        if self._pending:
            writable = min(len(self._pending), self._sink.bytesFree())
            if writable:
                written = self._device.write(self._pending[:writable])
                if written < 0:
                    self.stop()
                    self.error.emit("Audio output failed")
                    return
                self._pending = self._pending[written:]
        if self._eof and not self._pending and self._sink.bytesFree() >= self._sink.bufferSize():
            self.stop()
            self.finished.emit()
