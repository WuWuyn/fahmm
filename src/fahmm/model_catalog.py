"""Reviewed multilingual CTranslate2 Whisper models; no network access on import."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelChoice:
    name: str
    repository: str
    publisher: str
    license: str
    estimated_bytes: int
    revision: str
    resource_warning: str = ""


CATALOG = (
    ModelChoice(
        "Base (recommended for ordinary CPUs)",
        "Systran/faster-whisper-base",
        "Systran",
        "MIT",
        148_000_000,
        "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
    ),
    ModelChoice(
        "Small",
        "Systran/faster-whisper-small",
        "Systran",
        "MIT",
        486_000_000,
        "536b0662742c02347bc0e980a01041f333bce120",
    ),
    ModelChoice(
        "Medium",
        "Systran/faster-whisper-medium",
        "Systran",
        "MIT",
        1_530_000_000,
        "08e178d48790749d25932bbc082711ddcfdfbc4f",
        "Large download and slow CPU transcription; check available RAM and disk space.",
    ),
    ModelChoice(
        "Large v3 turbo",
        "deepdml/faster-whisper-large-v3-turbo-ct2",
        "deepdml",
        "MIT",
        1_620_000_000,
        "4df90f75321148c3a29a9e2351b7ddf8f5b115a8",
        "Large download and high RAM demand; may be unsuitable for an 8 GB CPU computer.",
    ),
)

BY_REPOSITORY = {choice.repository: choice for choice in CATALOG}
