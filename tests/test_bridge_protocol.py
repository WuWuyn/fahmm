"""The Python bridge accepts the same contract fixtures as desktop clients."""

import json
from pathlib import Path

import pytest

from fahmm.bridge.protocol import FrameError, validate_frame

FIXTURES = json.loads(
    (Path(__file__).resolve().parents[1] / "desktop" / "protocol" / "fixtures.json").read_text(
        encoding="utf-8"
    )
)


def test_shared_contract_fixtures():
    for frame in FIXTURES["valid"]:
        assert validate_frame(json.dumps(frame)) == frame
    for frame in FIXTURES["invalid"]:
        with pytest.raises(FrameError):
            validate_frame(json.dumps(frame))


def test_malformed_and_oversized_frames():
    for payload in (FIXTURES["malformed"], "x" * 1_048_577):
        with pytest.raises(FrameError):
            validate_frame(payload)
