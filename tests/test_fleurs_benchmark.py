"""The benchmark corpus must keep whole audio clips aligned with their text."""

import io
import json
import tarfile
import wave

import pytest

from scripts.build_fleurs_benchmark import RATE, build


def make_source(root, language, prefix):
    directory = root / language
    (directory / "audio").mkdir(parents=True)
    rows = []
    with tarfile.open(directory / "audio" / "dev.tar.gz", "w:gz") as archive:
        for index in range(2):
            name = f"{prefix}{index}.wav"
            rows.append(f"{index}\t{name}\t{prefix} text {index}\n")
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(RATE)
                audio.writeframes(b"\x01\x00" * (RATE // 4))
            data = buffer.getvalue()
            info = tarfile.TarInfo(f"dev/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    (directory / "dev.tsv").write_text("".join(rows), encoding="utf-8")


def test_complete_audio_and_transcript_are_kept_aligned(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    make_source(source, "vi_vn", "vi")
    make_source(source, "en_us", "en")
    result = build(source, output, minutes_per_language=0.01)
    assert result["fixtures"]["mixed"]["clips"] == 4
    assert (output / "mixed.txt").read_text(encoding="utf-8").splitlines() == [
        "vi text 0",
        "en text 0",
        "vi text 1",
        "en text 1",
    ]
    with wave.open(str(output / "mixed.wav"), "rb") as audio:
        assert audio.getframerate() == RATE and audio.getnchannels() == 1
        assert audio.getnframes() / RATE == pytest.approx(1.8)
    assert (
        json.loads((output / "manifest.json").read_text(encoding="utf-8"))["license"] == "CC BY 4.0"
    )
    with pytest.raises(FileExistsError):
        build(source, output, minutes_per_language=0.01)
