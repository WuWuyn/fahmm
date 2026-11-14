# M3 verification

## AT-05 — Restricted offline chain

**Result: passed on Windows x64, 14 November 2026.** `uv run pytest -q tests/test_at05.py -s` completed in 14.86 seconds. A controlled capture adapter supplied the first seconds of the licensed Vietnamese FLEURS sample used for M2's AT-03, recording a local stereo WAV through the M1 controller. The installed multilingual Base model transcribed the recording in a spawned worker with socket connections blocked and no `OPENAI_API_KEY` or `HF_TOKEN`. The offline service then saved an unverified, source-linked extractive minutes version. The meeting remained `restricted`; the main-process network spy recorded zero connection attempts.

The source archive, generated sample hash, model revision, and license are documented in [M2 verification](m2-verification.md). This test uses controlled audio through an adapter, not a live meeting or real speaker/microphone devices. M1's permitted 20-minute Teams/Meet recording, real Pause/Resume, and crash-recovery acceptance remain pending in [M1 verification](m1-verification.md).

## AT-06–AT-08 — Provider disclosure and failures

**Result: passed on Windows x64, 14 November 2026.** `uv run pytest -q tests/test_at06_08.py` completed in 4.92 seconds. A Restricted meeting rejected cloud preparation before the socket spy saw any connection. After changing the meeting to Cloud permitted, canceling confirmation sent no request. A confirmed send reached only the loopback host `127.0.0.1` and its JSON body contained the one selected, corrected transcript segment; it omitted the unselected segment and API key. The test did not persist the key or raw outgoing content as evidence.

The loopback provider then returned HTTP 429. The app reported a sanitized quota error, and byte comparisons showed the meeting's audio/transcript/minutes files were unchanged. The classification remained Cloud permitted. A later successful retry used a fresh request snapshot and confirmation, creating a second unverified version. Separate Qt tests verify that the full destination/payload preview appears before each Confirm/Cancel decision and that Retry presents it again.

## AT-09 — Unknown fields and source evidence

**Result: passed on Windows x64, 14 November 2026.** `uv run pytest -q tests/test_at09.py` completed in 2.33 seconds. A controlled transcript contained an explicit decision and task but no owner or deadline. Both offline and provider minutes used `Chưa rõ` for those fields. The decision cited the selected transcript segment's actual 0.0–2.0 second timestamp. An invented owner/deadline supplied by the fake provider was discarded; an out-of-range citation was removed and the statement remained flagged for review. Both versions remained unverified.

Source ID validation and exact-text checks cannot establish that a provider's statement truly follows from the cited audio. Human review, transcript navigation, and the unverified state remain necessary before approval.

## M1–M3 integration gate

**Result: passed on Windows x64, 14 November 2026.** `uv run pytest -q` passed all 84 tests in 419.17 seconds with exit code 0. `uv run fahmm --smoke` opened and closed the Windows application with exit code 0. `uv run ruff check .` and `openspec validate minutes-privacy-m3 --strict` passed.

The first combined pytest run reported 84 passing tests but exited with code 1 after test completion. AT-03 and the other 83 tests each exited successfully when run separately. Keeping a process-lifetime reference to AT-03's `QApplication` resolved the combined Qt teardown issue; the complete suite then exited successfully. The smoke run also passed when run separately from the long ASR test.

This gate uses controlled audio and a loopback provider. M1's permitted real-meeting/hardware acceptance remains open, and M4 export, deletion, packaging, and release acceptance are still planned.
