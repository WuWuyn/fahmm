# G1 candidate preparation — 2026-11-16

Status: **CANDIDATE PREPARED; G1 REAL-DEVICE TESTS NOT RUN**. This is build and integrity evidence for the [G1 procedure](../flow12-g1-test-procedure.md), not AT-01, AT-02 or AT-10 acceptance. No meeting audio or transcript was used.

| Item | Observed value |
| --- | --- |
| Code commit | `1352c90feeff95baf707938b712c28fc1a196e26` (`main`, clean before build) |
| Environment | Windows 11 x64 build 26200, development machine with Python/uv/Node/Rust installed |
| Candidate | `.build/release/fahmm-tauri-0.1.0-windows-x64-portable.zip` (local, ignored by Git) |
| ZIP SHA-256 | `8617a26b5cb48a97219309afbf7bfe19f6ade90de200da8a5f4b2b886e28c0db` |
| ZIP size | 108,805,419 bytes |
| Manifest | `BUILD_INFO.json` extracted from ZIP: `sourceRevision` matches code commit; `sourceDirty: false` |
| Embedded host SHA-256 | `e6c944a9e38b3d6b994ed82903e32c6355740c0bff1a22cb3b7b69daece9b2d7`; matches manifest |
| Embedded sidecar SHA-256 | `52a586197ca338853d1e89fe82fd87c5413950c5129a1df92ff7943fb24600e5`; matches manifest |

| Preparation check | Result |
| --- | --- |
| `uv run --locked --offline --group build python scripts/build_sidecar.py` with uv on PATH | exit 0; PyInstaller build, worker smoke and JSON-lines health passed |
| `npm run tauri build -- --no-bundle` | exit 0; frontend and release host built |
| `uv run --locked --offline python scripts/package_tauri_portable.py` | exit 0; clean-source package, `.sha256` file created |
| ZIP extraction and SHA comparison | exit 0; both executable hashes and source revision match manifest |
| `uv run --locked --offline python scripts/verify_tauri_sidecar.py --offline-only` | exit 0; offline/no-key, restart, media ticket and local document flow passed; provider cases not run |

The earlier `2211d44` ZIP (SHA-256 `535faa477ea0cbf955668a6e428b8ac9ea369d3bcb3140adb0f411225791f3d3`) was preserved under `.build/release/archive-2211d44/` before the standard output filename was reused. The new Tauri host has not been launched for a real-device recording or checked on clean Windows 10/11 machines. It is not a release artifact.

Local ignored log SHA-256 values: `sidecar.log` `35E4ACAC6F24D1A4B40FAFBBF0A060019D9836D3EB6D4128CDD7189480EC9790`; `tauri-build.log` `814FC929262EC0052DD3A9F09F97F9F1FA70CBB30096D086E30EC9ACEA44274D`; `package.log` `4C1C42419E56C253A8E7C18A4A5F639C4C1C9BC604C0A1AC4A02FD6E36C4D97E`; `frozen-sidecar-smoke.log` `01F8D93FE17F6C79EC5E339B5CC68CE4E08493B7A76ED8F85293EA3C1D27E12A`.

Tester: Codex (automated preparation). Listener: pending. Engineering reviewer: pending. Product owner: pending.
