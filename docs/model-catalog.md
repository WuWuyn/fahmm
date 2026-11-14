# Recommended local ASR models

The Models screen offers these multilingual CTranslate2 Whisper bundles. File sizes are estimates from the publishers' Hugging Face file listings, checked on 14 November 2026. Downloads use the pinned revisions below, so a later upstream change cannot silently alter an installed model. The app's MIT license does not replace the model publishers' licenses.

| Model | Repository and publisher | Declared license | Estimated size | Pinned revision |
| --- | --- | --- | ---: | --- |
| Base | [Systran/faster-whisper-base](https://huggingface.co/Systran/faster-whisper-base/tree/main) · Systran | MIT | 148 MB | `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66` |
| Small | [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small/tree/main) · Systran | MIT | 486 MB | `536b0662742c02347bc0e980a01041f333bce120` |
| Medium | [Systran/faster-whisper-medium](https://huggingface.co/Systran/faster-whisper-medium/tree/main) · Systran | MIT | 1.53 GB | `08e178d48790749d25932bbc082711ddcfdfbc4f` |
| Large v3 turbo | [deepdml/faster-whisper-large-v3-turbo-ct2](https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2/tree/main) · deepdml | MIT | 1.62 GB | `4df90f75321148c3a29a9e2351b7ddf8f5b115a8` |

Base is the default recommendation for an ordinary CPU. Medium and turbo require much more disk space and memory and may run slowly or fail on an 8 GB machine. The app must show a warning before those downloads. All four listings include `model.bin`, `config.json`, and `tokenizer.json`; Systran bundles include `vocabulary.txt`, while the turbo bundle includes `vocabulary.json` and `preprocessor_config.json`. A listed repository is a candidate only: installation still validates its local files before selection.

## Download and offline privacy

Opening Models and selecting an installed model do not contact Hugging Face. Clicking **Download selected model** requests only repository metadata and allowlisted model files; it never attaches a meeting ID, audio, transcript, or minutes. A failed transfer remains outside the installed list and can be retried. Once installed, ASR uses the local directory and works without an API key or network access. Deleting an unused model removes only its managed installation, not meeting files.
