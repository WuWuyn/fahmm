# Third-party notices and release review

This file accompanies a **release candidate for testing**. It is not a completed redistribution review. The exact Windows dependency versions are in `RUNTIME_DEPENDENCIES.txt`; `LICENSE_INVENTORY.json` names each installed runtime distribution and every wheel-provided notice copied into `LICENSES/`. Those files are packaged beside the executable. No Whisper model weights are included.

| Component | License evidence | Packaging note |
| --- | --- | --- |
| PySide6 / Qt 6 | [Qt for Python licensing](https://doc.qt.io/qtforpython-6/) and [Qt licensing](https://doc.qt.io/qt-6/licensing.html) | Community packages use LGPLv3/GPLv3 options; bundled Qt DLLs and plugins require a complete component-level notice and relinking review before public distribution. |
| PyAV | [PyAV license](https://pyav.org/docs/stable/development/license.html) | PyAV source is BSD-3-Clause. Its Windows wheel also carries FFmpeg and codec DLLs, so that source license alone does not describe the binary package. |
| FFmpeg and codecs inside the PyAV wheel | [PyAV FFmpeg binary build](https://github.com/PyAV-Org/pyav-ffmpeg) and [upstream GPL wheel discussion](https://github.com/PyAV-Org/PyAV/issues/2270) | The installed wheel includes `libx264` and `libx265` DLLs. GPL obligations and corresponding source/notice delivery for the exact build must be resolved before publishing this ZIP. |
| faster-whisper | [Upstream license](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) | MIT source; model weights are separately licensed and are not redistributed here. |
| CTranslate2 | [Upstream license](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) | MIT source; native binaries and their linked dependencies need exact-wheel review. |
| SoundCard | [Upstream license](https://github.com/bastibe/SoundCard/blob/master/LICENSE) | BSD-3-Clause source; wheel notice is copied into `LICENSES/`. |
| Hugging Face Hub and tokenizers | [Hub license](https://github.com/huggingface/huggingface_hub/blob/main/LICENSE) and [tokenizers license](https://github.com/huggingface/tokenizers/blob/main/LICENSE) | Apache-2.0 source; verify exact wheel and native components against the inventory. |
| OpenAI Python SDK | [Upstream license](https://github.com/openai/openai-python/blob/main/LICENSE) | Apache-2.0 source; the SDK is optional at runtime and sends content only after explicit per-request confirmation. |
| Python 3.12 runtime and PyInstaller bootloader | [Python license](https://docs.python.org/3/license.html) and [PyInstaller license](https://pyinstaller.org/en/stable/license.html) | The frozen app embeds a Python runtime and bootloader; exact binary notices and distribution terms still need review. |
| NumPy, ONNX Runtime, and transitive packages | See wheel-provided notices in `LICENSES/` and versions in `LICENSE_INVENTORY.json` | Review any missing notices and native linked components before redistribution. |
| Impeccable agent skill in `.agents/skills/impeccable/` | [Upstream repository and Apache-2.0 license](https://github.com/pbakaus/impeccable) | Development tooling only; the skill files and executable are not bundled into the fahmm desktop installer. The license is retained beside the installed skill. |

The current locked runtime inventory has no wheel-provided license file for CTranslate2, flatbuffers, the PySide6/Shiboken distributions, or tokenizers. Upstream links above identify some terms but do not replace an exact binary notice review. `PySide6_Pdf` and `PySide6_WebEngine` are lockfile dependencies; the ZIP inventory must distinguish them from modules actually collected by PyInstaller.

**Release hold:** Do not publish or present this candidate as a completed v1 release until the PyAV/FFmpeg codec licensing, Qt component notices, and all transitive native notices have been reviewed against the exact ZIP. The executable is suitable for local packaging and functional testing while this review is pending.
