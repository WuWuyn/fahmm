"""Build reproducible Vietnamese/English ASR fixtures from local FLEURS dev files.

This never downloads data and never extracts archive paths. Use only archives and
TSV references from the same pinned revision. Each selected utterance is kept
whole so the reference cannot include words cut off from the audio.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import tarfile
import wave
from pathlib import Path, PurePosixPath

import av

RATE = 16_000
SILENCE = RATE // 5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def references(path: Path) -> dict[str, str]:
    result = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.reader(source, delimiter="\t"):
            if len(row) < 3 or not row[1].endswith(".wav") or not row[2].strip():
                raise ValueError("Invalid FLEURS reference row")
            if row[1] in result:
                raise ValueError("Duplicate FLEURS audio filename")
            result[row[1]] = row[2].strip()
    return result


def decode_wav(encoded: bytes) -> bytes:
    converted_frames = []
    with av.open(io.BytesIO(encoded), mode="r") as audio:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        for frame in audio.decode(audio=0):
            converted_frames.extend(resampler.resample(frame))
        converted_frames.extend(resampler.resample(None))
    return b"".join(frame.to_ndarray().tobytes()[: frame.samples * 2] for frame in converted_frames)


def prepare_bank(archive: Path, tsv: Path, destination: Path, frames_target: int) -> list[dict]:
    texts = references(tsv)
    clips = []
    duration = 0
    with tarfile.open(archive, "r:gz") as source, destination.open("xb") as bank:
        for member in source:
            name = PurePosixPath(member.name).name
            if not member.isfile() or member.name != f"dev/{name}" or name not in texts:
                continue
            extracted = source.extractfile(member)
            if extracted is None:
                continue
            pcm = decode_wav(extracted.read())
            if not pcm or len(pcm) % 2:
                raise ValueError("Invalid or empty FLEURS audio")
            clips.append(
                {"name": name, "offset": bank.tell(), "bytes": len(pcm), "text": texts[name]}
            )
            bank.write(pcm)
            duration += len(pcm) // 2 + SILENCE
            if duration >= frames_target:
                break
    if duration < frames_target:
        raise ValueError("A FLEURS archive has less matched speech than requested")
    return clips


def write_fixture(
    target: Path, reference: Path, order: list[tuple[str, dict]], banks: dict[str, Path]
) -> float:
    handles = {language: path.open("rb") for language, path in banks.items()}
    frames = 0
    try:
        with wave.open(str(target), "wb") as audio, reference.open("x", encoding="utf-8") as text:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(RATE)
            for language, clip in order:
                bank = handles[language]
                bank.seek(clip["offset"])
                pcm = bank.read(clip["bytes"])
                if len(pcm) != clip["bytes"]:
                    raise ValueError("Incomplete benchmark audio bank")
                audio.writeframesraw(pcm)
                audio.writeframesraw(b"\0\0" * SILENCE)
                frames += len(pcm) // 2 + SILENCE
                text.write(clip["text"] + "\n")
    finally:
        for handle in handles.values():
            handle.close()
    return frames / RATE


def build(
    source: Path, output: Path, minutes_per_language: float, dataset_revision: str | None = None
) -> dict:
    if minutes_per_language <= 0:
        raise ValueError("Minutes per language must be positive")
    files = {
        language: (source / language / "audio" / "dev.tar.gz", source / language / "dev.tsv")
        for language in ("vi_vn", "en_us")
    }
    if any(not path.is_file() for pair in files.values() for path in pair):
        raise ValueError("Both FLEURS dev archives and TSV files are required")
    output.mkdir(parents=False, exist_ok=False)
    banks = {language: output / f"{language}.pcm" for language in files}
    target_frames = round(minutes_per_language * 60 * RATE)
    clips = {
        language: prepare_bank(archive, tsv, banks[language], target_frames)
        for language, (archive, tsv) in files.items()
    }
    fixtures = {}
    for language in files:
        order = [(language, item) for item in clips[language]]
        seconds = write_fixture(
            output / f"{language}.wav", output / f"{language}.txt", order, banks
        )
        fixtures[language] = {"seconds": seconds, "clips": len(order)}
    mixed = []
    for index in range(max(map(len, clips.values()))):
        for language in files:
            if index < len(clips[language]):
                mixed.append((language, clips[language][index]))
    seconds = write_fixture(output / "mixed.wav", output / "mixed.txt", mixed, banks)
    fixtures["mixed"] = {"seconds": seconds, "clips": len(mixed)}
    manifest = {
        "dataset": "Google FLEURS dev (vi_vn and en_us)",
        "source": "https://huggingface.co/datasets/google/fleurs",
        "license": "CC BY 4.0",
        "dataset_revision": dataset_revision,
        "note": "Read utterances concatenated with 0.2s silence; mixed alternates languages, not a real bilingual meeting",
        "inputs": {
            language: {
                "archive_sha256": sha256(pair[0]),
                "tsv_sha256": sha256(pair[1]),
                "clips": [item["name"] for item in clips[language]],
            }
            for language, pair in files.items()
        },
        "fixtures": fixtures,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for path in banks.values():
        path.unlink()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Local FLEURS data directory containing vi_vn and en_us"
    )
    parser.add_argument("output", type=Path, help="New destination directory")
    parser.add_argument("--minutes-per-language", type=float, default=35)
    parser.add_argument("--revision", help="Dataset revision of the downloaded inputs")
    args = parser.parse_args()
    result = build(args.source, args.output, args.minutes_per_language, args.revision)
    print(json.dumps(result["fixtures"], indent=2))


if __name__ == "__main__":
    main()
