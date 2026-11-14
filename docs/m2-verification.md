# M2 verification

## Integration and regression

**Result: passed on Windows x64, 14 November 2026.** `uv run pytest -q` completed with **38 passed in 323.01 seconds**, covering M1 recording/recovery and M2 import, transcription, model management, and transcript review. `uv run fahmm --smoke` opened and closed the Windows app successfully; `uv run ruff check .` and `openspec validate local-asr-m2 --strict` passed. The remaining M1 real-meeting and live hardware acceptance checks are tracked separately in [M1 verification](m1-verification.md).

## AT-03 — Offline long Vietnamese audio

**Result: passed on Windows x64, 14 November 2026.** `uv run pytest tests/test_at03.py -q -s` completed in 314.51 seconds. The test imported a 1,800-second WAV through the English Meetings screen, selected the installed multilingual Base model, and completed local transcription with **195 timestamped segments**; the last segment ended at 1,799 seconds. The UI's Qt timer continued to run during processing. The meeting remained `restricted`, and its processing state became `completed`. The ASR worker had socket connections blocked and no `OPENAI_API_KEY` or `HF_TOKEN`.

**Sample provenance:** [Google FLEURS, Vietnamese `vi_vn` dev audio](https://huggingface.co/datasets/google/fleurs/tree/main/data/vi_vn/audio), licensed [CC BY 4.0](https://huggingface.co/datasets/google/fleurs). `scripts/build_fleurs_sample.py` joined 152 distinct dev clips into one 30-minute, 16 kHz mono WAV; the sample is kept outside the repository under the local fahmm acceptance directory. Source archive SHA-256: `8821a394c99069409b3ce7bb5cd14b10b709f2ee2fea16f42b4701e1cc9ef673`. Generated WAV SHA-256: `22914aa07bb2a24fe56ea88650c58e8f0901111798cf9d3934823d702510205b`. The ASR model revision was `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`.

This fixture tests a long file and varied Vietnamese speech, but its clips are concatenated read speech, not a live meeting. It does not establish meeting-noise or accent accuracy. M1's real-meeting hardware tests remain pending separately.

## AT-04 — Hugging Face model management

**Result: passed on Windows x64, 14 November 2026.** `uv run python scripts/verify_at04.py` contacted Hugging Face only for an explicit test download. [Systran/faster-whisper-tiny](https://huggingface.co/Systran/faster-whisper-tiny/tree/main) installed as a compatible custom CT2 model at revision `d90ca5fe260221311c53c58e660288d3deb8d356` (78,203,619 downloaded bytes); the progress callback reported 43 updates. Selection persisted after reopening the model manager. A second download request reused the installed model with socket connections blocked, and deletion removed its managed files. The separate installed Base model and meeting data were untouched.

[deepdml/whisper-large-v3-turbo](https://huggingface.co/deepdml/whisper-large-v3-turbo/tree/main), a Transformers/Safetensors repository without CT2 `model.bin`, was rejected after metadata inspection with “Repository is not a complete CTranslate2 Whisper model”; its weights were not downloaded. The machine-local result JSON is under the fahmm acceptance directory.
