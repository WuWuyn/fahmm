from contextlib import nullcontext

import numpy as np
import pytest

from fahmm.audio import DeviceUnavailable, SoundCardCapture


class FakeMicrophone:
    def __init__(self, identifier, loopback):
        self.id = identifier
        self.name = identifier
        self.isloopback = loopback
        self.opened = False

    def recorder(self, **kwargs):
        self.opened = True
        return nullcontext()


def test_list_and_open_exact_selected_source(monkeypatch):
    system = FakeMicrophone("speaker-id", True)
    mic = FakeMicrophone("mic-id", False)
    capture = SoundCardCapture()
    monkeypatch.setattr(capture, "_microphones", lambda: [system, mic])
    monkeypatch.setattr(
        capture, "_default_ids", lambda: {"system": "speaker-id", "microphone": "mic-id"}
    )
    devices = capture.list_devices()
    assert [item.id for item in devices["system"]] == ["speaker-id"]
    assert [item.id for item in devices["microphone"]] == ["mic-id"]
    assert not system.opened and not mic.opened
    capture.open("system", "speaker-id")
    assert system.opened and not mic.opened
    with pytest.raises(DeviceUnavailable):
        capture.open("microphone", "speaker-id")


def test_windows_defaults_precede_virtual_and_other_devices(monkeypatch):
    virtual_mic = FakeMicrophone("virtual-mic", False)
    speakers = FakeMicrophone("speakers", True)
    headset = FakeMicrophone("headset", False)
    default_mic = FakeMicrophone("default-mic", False)
    default_output = FakeMicrophone("default-output", True)
    capture = SoundCardCapture()
    all_devices = [virtual_mic, speakers, headset, default_mic, default_output]
    monkeypatch.setattr(capture, "_microphones", lambda: all_devices)
    monkeypatch.setattr(
        capture,
        "_default_ids",
        lambda: {
            "system": "default-output",
            "microphone": "default-mic",
        },
    )

    devices = capture.list_devices()

    assert [device.id for device in devices["system"]] == ["default-output", "speakers"]
    assert [device.id for device in devices["microphone"]] == [
        "default-mic",
        "virtual-mic",
        "headset",
    ]
    assert not any(device.opened for device in all_devices)


def test_stream_downmixes_multichannel():
    class Recorder:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def record(self, numframes):
            return np.tile([0.25, 0.75], (numframes, 1))

    from fahmm.audio import _SoundCardStream

    with _SoundCardStream(Recorder()) as stream:
        assert np.allclose(stream.read(10), 0.5)
