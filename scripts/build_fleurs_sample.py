"""Build a local AT-03 fixture from Google FLEURS Vietnamese dev speech (CC BY 4.0)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import wave
from pathlib import Path

import av

SOURCE_URL = "https://huggingface.co/datasets/google/fleurs/tree/main/data/vi_vn/audio"
SAMPLE_RATE = 16_000


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_sample(source: Path, output: Path, minutes: int = 30) -> dict:
    if not 30 <= minutes <= 60:
        raise ValueError("AT-03 requires a 30–60-minute sample")
    target_frames = minutes * 60 * SAMPLE_RATE
    output.parent.mkdir(parents=True, exist_ok=True)
    selected = []
    written = 0
    with tarfile.open(source, "r:gz") as archive, wave.open(str(output), "wb") as result:
        result.setnchannels(1)
        result.setsampwidth(2)
        result.setframerate(SAMPLE_RATE)
        for member in sorted(archive.getmembers(), key=lambda item: item.name):
            if not member.isfile() or not member.name.endswith(".wav"):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            selected.append(member.name)
            with av.open(io.BytesIO(extracted.read()), mode="r") as container:
                resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
                for frame in container.decode(audio=0):
                    for converted in resampler.resample(frame):
                        remaining = target_frames - written
                        if remaining <= 0:
                            break
                        count = min(remaining, converted.samples)
                        result.writeframesraw(converted.to_ndarray().tobytes()[: count * 2])
                        written += count
                for converted in resampler.resample(None):
                    remaining = target_frames - written
                    if remaining <= 0:
                        break
                    count = min(remaining, converted.samples)
                    result.writeframesraw(converted.to_ndarray().tobytes()[: count * 2])
                    written += count
            if written >= target_frames:
                break
            pause = min(SAMPLE_RATE // 5, target_frames - written)
            result.writeframesraw(b"\0\0" * pause)
            written += pause
    if written < target_frames:
        output.unlink(missing_ok=True)
        raise ValueError("The source archive has less speech than the requested duration")
    manifest = {
        "source": SOURCE_URL,
        "dataset": "Google FLEURS vi_vn dev",
        "license": "CC BY 4.0",
        "archive_sha256": file_hash(source),
        "sample_sha256": file_hash(output),
        "duration_seconds": written / SAMPLE_RATE,
        "clip_count": len(selected),
        "clips": selected,
    }
    output.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Downloaded vi_vn/audio/dev.tar.gz")
    parser.add_argument("output", type=Path, help="Local 30-minute WAV destination")
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()
    result = build_sample(args.source, args.output, args.minutes)
    print(f"Created {args.output}: {result['duration_seconds']:.0f}s, {result['clip_count']} clips")


if __name__ == "__main__":
    main()
