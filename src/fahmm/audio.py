"""Windows WASAPI capture adapter. Listing devices never opens a recorder."""

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, Self

import numpy as np

from fahmm.storage import SAMPLE_RATE


@dataclass(frozen=True)
class AudioDevice:
    id: str
    name: str


class AudioStream(Protocol):
    def read(self, frames: int) -> np.ndarray: ...


class AudioCapture(Protocol):
    def list_devices(self) -> dict[str, list[AudioDevice]]: ...
    def open(self, source: str, device_id: str) -> AbstractContextManager[AudioStream]: ...


class DeviceUnavailable(RuntimeError):
    pass


class _SoundCardStream:
    def __init__(self, recorder: object) -> None:
        self.recorder = recorder

    def __enter__(self) -> Self:
        self.recorder.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.recorder.__exit__(exc_type, exc, tb)

    def read(self, frames: int) -> np.ndarray:
        data = np.asarray(self.recorder.record(numframes=frames), dtype=np.float32)
        if data.ndim == 2:
            data = data.mean(axis=1)
        if data.ndim != 1 or not np.isfinite(data).all():
            raise RuntimeError("The device returned invalid audio")
        return data


class SoundCardCapture:
    def _microphones(self) -> list:
        if os.name != "nt":
            raise RuntimeError("M1 supports recording on Windows only")
        import soundcard as sc

        return sc.all_microphones(include_loopback=True)

    def _default_ids(self) -> dict[str, str | None]:
        import soundcard as sc

        defaults: dict[str, str | None] = {}
        for source, get_default in (
            ("system", sc.default_speaker),
            ("microphone", sc.default_microphone),
        ):
            try:
                device = get_default()
                defaults[source] = str(device.id) if device is not None else None
            except Exception:
                # A missing Windows default must not hide the other available devices.
                defaults[source] = None
        return defaults

    def list_devices(self) -> dict[str, list[AudioDevice]]:
        devices = self._microphones()
        result = {
            "system": [AudioDevice(str(item.id), item.name) for item in devices if item.isloopback],
            "microphone": [
                AudioDevice(str(item.id), item.name) for item in devices if not item.isloopback
            ],
        }
        defaults = self._default_ids()
        for source, items in result.items():
            items.sort(key=lambda item: item.id != defaults[source])
        return result

    def open(self, source: str, device_id: str) -> _SoundCardStream:
        if source not in ("system", "microphone"):
            raise ValueError("Invalid audio source")
        devices = self._microphones()
        matched = next(
            (
                item
                for item in devices
                if str(item.id) == device_id and bool(item.isloopback) == (source == "system")
            ),
            None,
        )
        if matched is None:
            label = "system audio" if source == "system" else "microphone"
            raise DeviceUnavailable(f"The selected {label} device is unavailable")
        try:
            recorder = matched.recorder(samplerate=SAMPLE_RATE, blocksize=4096)
            return _SoundCardStream(recorder)
        except Exception as exc:
            label = "system audio" if source == "system" else "microphone"
            raise DeviceUnavailable(f"Cannot open {label}: {exc}") from exc
