# v1 Tauri native package review

Status: **incomplete; do not publish**. Candidate source revision `2211d4494408bcb80897a861f256e58b42b6b698`; frozen sidecar SHA-256 `26bbc79b1e41714ac65248b4f5161751db58b0a8d7bb9f672ea2819b302ca636`. This inventory was taken from that sidecar, not from the older Qt package.

## Observed package contents

The MSI administrative image contains `fahmm-desktop.exe` and `fahmm-sidecar.exe`. The portable ZIP contains the same two executable roles, `BUILD_INFO.json`, and a short README. The sidecar hash in the MSI matches the standalone sidecar. See the [complete PyInstaller archive listing](v1-sidecar-archive.txt): 523 archive entries, 175 native `.dll`/`.pyd` entries, and 24 paths named as license or notice material. The listing contains no `model.bin` or audio file. It is an inventory of names, not proof that every linked component or obligation has been identified.

| Native group found in the sidecar | Evidence | Review still required |
| --- | --- | --- |
| Python 3.12 runtime and PyInstaller bootloader | `python312.dll`, Python extension `.pyd` files, one-file executable | Exact runtime and bootloader notices in the delivered package |
| PyAV 18.1.0 and FFmpeg | `av.libs` includes `avcodec`, `avformat`, `avutil`, `libx264`, `libx265`, and other codec DLLs | Exact binary build terms, corresponding source, attribution, and distribution obligations |
| CTranslate2 4.9.0 | `ctranslate2.dll`, `_ext.pyd`, `cudnn64_9.dll`, `libiomp5md.dll` | Notices and redistribution terms for the exact CTranslate2, NVIDIA, and Intel binaries |
| ONNX Runtime | `onnxruntime.dll`, provider DLL, Python binding | Include exact wheel license and third-party notices; identify whether this runtime is required by the v1 features |
| Tokenizers and NumPy | `tokenizers.pyd`, NumPy extensions and OpenBLAS DLL | Match exact wheel notices to shipped binaries |
| Tauri host | MSI and ZIP each contain the compiled Rust host; the WebView is supplied by Windows | Resolve host crate, frontend asset, icon, and WebView runtime notices for the final package |

## PyAV/FFmpeg ambiguity that blocks distribution

The installed PyAV wheel's `avcodec_license()` reports `LGPL version 3 or later`. Its `avcodec_configuration()` reports `--enable-version3`, `--enable-libx264`, and `--enable-libx265`, without `--enable-gpl`. The archived `avcodec` DLL and installed wheel DLL have the same SHA-256, `777704d8914bb99e5d78f3a0e7424031b5376621f2e7c60e83b84e77fcc7e2d7`, so this check applies to the candidate's exact DLL. The exact DLL names are in the archive listing. [PyAV's binary build project](https://github.com/PyAV-Org/pyav-ffmpeg/blob/master/README.md) lists x264 and x265 among enabled dependencies. [FFmpeg's legal guidance](https://ffmpeg.org/legal.html) and [external-library documentation](https://ffmpeg.org/general.html) say use of these libraries can change the applicable FFmpeg license. These observed facts do not establish a compliant redistribution path for this exact wheel. Obtain authoritative build provenance and terms for this wheel, or replace it with a reviewed build, before publishing either installer or ZIP.

## Notice gap and release gate

The frozen archive contains some wheel notices, including PyAV and NumPy material, but no paths named as notices for FFmpeg, x264, x265, CTranslate2, cuDNN, Intel OpenMP, ONNX Runtime, Python, or the Tauri host. The current internal ZIP does not contain a consolidated notice bundle. Upstream source licenses, such as [CTranslate2](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) and [ONNX Runtime](https://github.com/microsoft/onnxruntime/blob/main/LICENSE), help identify sources but do not by themselves resolve the terms of every bundled native binary. The [CTranslate2 Windows build recipe](https://github.com/OpenNMT/CTranslate2/blob/master/python/tools/prepare_build_environment_windows.sh) explicitly copies cuDNN and Intel runtime DLLs into its Python wheel.

Before public distribution, map each native and frontend component in the **final hashed package** to its exact source, version, license, required notices, and source or relinking offer where applicable. Include those materials in both package formats, verify the notice inventory against the archive, then rebuild and rerun acceptance on the new hashes. This review is a release gate, not a legal conclusion.
