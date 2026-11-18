// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TranscriptPanel } from "@/features/transcript/TranscriptPanel";
import { bridgeCall, exportAudio, exportSaved } from "@/shared/bridge/client";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn(), exportAudio: vi.fn(), exportSaved: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("starts at the selected playhead or defaults to the beginning of the selected meeting", async () => {
  const user = userEvent.setup();
  const meetingId = "a".repeat(32);
  const modelId = "m".repeat(32);
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "transcript.list") return { runs: [], activeRunId: null };
    if (operation === "model.catalog") return { selectedId: modelId };
    if (operation === "asr.status") return { state: "idle", meetingId: null, runId: null, progress: null, segmentCount: 0, error: null };
    if (operation === "asr.startFrom") return { runId: "r".repeat(32) };
    throw new Error(`Unexpected operation ${operation}`);
  });
  render(<TranscriptPanel meetingId={meetingId} onSeek={() => {}} onRunChange={() => {}}
    playheadSeconds={12.8} audioDurationSeconds={65} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Transcribe" }).hasAttribute("disabled")).toBe(false));
  await user.click(screen.getByRole("button", { name: "Use playback position" }));
  expect((screen.getByRole("textbox", { name: "Start transcription at" }) as HTMLInputElement).value).toBe("00:12.8");
  await user.click(screen.getByRole("button", { name: "Transcribe" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
    operation === "asr.startFrom" && params?.meetingId === meetingId && params?.startSeconds === 12.8)).toBe(true));

  await user.clear(screen.getByRole("textbox", { name: "Start transcription at" }));
  await user.click(screen.getByRole("button", { name: "Transcribe" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.filter(([operation]) => operation === "asr.startFrom")).toHaveLength(2));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
    operation === "asr.startFrom" && params?.startSeconds === 0)).toBe(true);

  await user.type(screen.getByRole("textbox", { name: "Start transcription at" }), "01:05");
  await user.click(screen.getByRole("button", { name: "Transcribe" }));
  expect(screen.getByText(/Choose a start time before the end/)).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.filter(([operation]) => operation === "asr.startFrom")).toHaveLength(2);
});

it("saves timestamped corrections while retaining original ASR through a remount", async () => {
  const user = userEvent.setup();
  const runId = "r".repeat(32);
  let saved = "Xin chào";
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "transcript.list") return { runs: [{ run_id: runId, created_at: "2026-11-14T00:00:00Z", model_repository: "test/base" }], activeRunId: runId };
    if (operation === "model.catalog") return { selectedId: "m".repeat(32) };
    if (operation === "transcript.read") return { run: { manifest: { run_id: runId, created_at: "2026-11-14T00:00:00Z", model_repository: "test/base" },
      original: [{ id: 1, start: 12, end: 15, text: "Xin chào" }], working: [{ id: 1, start: 12, end: 15, text: saved }] } };
    if (operation === "transcript.saveEdits") { saved = String((params?.edits as Record<string, string>)["1"]); return { saved: true }; }
    if (operation === "asr.status") return { state: "idle", meetingId: null, runId: null, progress: null, segmentCount: 0, error: null };
    throw new Error(`Unexpected operation ${operation}`);
  });
  const selected: number[] = [];
  const view = render(<TranscriptPanel meetingId={"a".repeat(32)} onSeek={(seconds) => selected.push(seconds)} onRunChange={() => {}} />);
  await screen.findByRole("textbox", { name: "Transcript segment 1" });
  await user.click(screen.getByRole("button", { name: /00:12/ }));
  expect(selected).toEqual([12]);
  await user.clear(screen.getByRole("textbox", { name: "Transcript segment 1" }));
  await user.type(screen.getByRole("textbox", { name: "Transcript segment 1" }), "Chào bạn");
  await user.click(screen.getByRole("button", { name: "Save edits" }));
  await waitFor(() => expect(saved).toBe("Chào bạn"));
  view.unmount();
  render(<TranscriptPanel meetingId={"a".repeat(32)} onSeek={() => {}} onRunChange={() => {}} />);
  await waitFor(() => expect((screen.getByRole("textbox", { name: "Transcript segment 1" }) as HTMLTextAreaElement).value).toBe("Chào bạn"));
  expect(screen.getByText("Original ASR: Xin chào")).toBeTruthy();
});

it("offers retry after ASR failure while leaving the prior saved run visible", async () => {
  const user = userEvent.setup();
  const runId = "r".repeat(32);
  const meetingId = "a".repeat(32);
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "transcript.list") return { runs: [{ run_id: runId, created_at: "2026-11-14T00:00:00Z", model_repository: "test/base" }], activeRunId: runId };
    if (operation === "model.catalog") return { selectedId: "m".repeat(32) };
    if (operation === "transcript.read") return { run: { manifest: { run_id: runId, created_at: "2026-11-14T00:00:00Z", model_repository: "test/base" },
      original: [{ id: 1, start: 0, end: 1, text: "Prior result" }], working: [{ id: 1, start: 0, end: 1, text: "Prior result" }] } };
    if (operation === "asr.status") return { state: "error", meetingId, runId: null, progress: 0.4, segmentCount: 0, error: "Transcription failed" };
    if (operation === "asr.retry") return { runId: "n".repeat(32) };
    throw new Error(`Unexpected operation ${operation}`);
  });
  render(<TranscriptPanel meetingId={meetingId} onSeek={() => {}} onRunChange={() => {}} />);
  await screen.findByText("Transcription failed");
  expect((await screen.findByRole("textbox", { name: "Transcript segment 1" }) as HTMLTextAreaElement).value).toBe("Prior result");
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "asr.retry")).toBe(true);
});

it("does not export unsaved transcript text and treats a native dialog cancel as no output", async () => {
  const user = userEvent.setup();
  const runId = "r".repeat(32);
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "transcript.list") return { runs: [{ run_id: runId, created_at: "2026-11-14T00:00:00Z", model_repository: "test/base" }], activeRunId: runId };
    if (operation === "model.catalog") return { selectedId: "m".repeat(32) };
    if (operation === "transcript.read") return { run: { manifest: { run_id: runId, created_at: "2026-11-14T00:00:00Z", model_repository: "test/base" },
      original: [{ id: 1, start: 0, end: 1, text: "Xin chào" }], working: [{ id: 1, start: 0, end: 1, text: "Xin chào" }] } };
    if (operation === "asr.status") return { state: "idle", meetingId: null, runId: null, progress: null, segmentCount: 0, error: null };
    throw new Error(`Unexpected operation ${operation}`);
  });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  vi.mocked(exportSaved).mockResolvedValue({ cancelled: true });
  render(<TranscriptPanel meetingId={"a".repeat(32)} onSeek={() => {}} onRunChange={() => {}} />);
  await screen.findByRole("textbox", { name: "Transcript segment 1" });
  await user.type(screen.getByRole("textbox", { name: "Transcript segment 1" }), " unsaved");
  await user.click(screen.getByRole("button", { name: "Export plain TXT" }));
  expect(vi.mocked(exportSaved)).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  await user.click(screen.getByRole("button", { name: "Export plain TXT" }));
  await waitFor(() => expect(vi.mocked(exportSaved)).toHaveBeenCalledWith("a".repeat(32), runId, "transcriptPlain"));
  expect(screen.queryByText(/Exported transcript/)).toBeNull();
  expect(screen.queryByText("Unsaved edits")).toBeNull();
  confirm.mockRestore();
});

it("exports recording audio even when no transcript exists", async () => {
  const user = userEvent.setup();
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "transcript.list") return { runs: [], activeRunId: null };
    if (operation === "model.catalog") return { selectedId: null };
    if (operation === "asr.status") return { state: "idle", meetingId: null, runId: null, progress: null, segmentCount: 0, error: null };
    throw new Error(`Unexpected operation ${operation}`);
  });
  vi.mocked(exportAudio).mockResolvedValue({ saved: true, displayName: "recording.wav" });
  render(<TranscriptPanel meetingId={"a".repeat(32)} onSeek={() => {}} onRunChange={() => {}} />);
  await user.click(await screen.findByRole("button", { name: "Export audio" }));
  expect(vi.mocked(exportAudio)).toHaveBeenCalledWith("a".repeat(32));
  expect(await screen.findByText("Exported recording.wav.")).toBeTruthy();
});
