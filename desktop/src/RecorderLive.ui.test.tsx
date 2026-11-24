// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Recorder } from "@/features/recorder/Recorder";
import { bridgeCall } from "@/shared/bridge/client";
import { useUIStore } from "@/shared/uiStore";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn() }));

const meetingA = "a".repeat(32);
const meetingB = "b".repeat(32);
const modelId = "c".repeat(32);
const runA = "d".repeat(32);
const runB = "e".repeat(32);
let recordingState: string;
let meetingId: string | null;
let failLiveStart: boolean;
let liveStatus: { state: string; meetingId: string | null; runId: string | null; cursorSeconds: number; segmentCount: number; provisionalCount: number; reviewWindows: number; errorCode: string | null; captureStatus: string | null; backlogSeconds: number | null };
let runLists: Record<string, { runId: string; state: string; cursorSeconds?: number; errorCode?: string | null }[]>;
let words: Record<string, { id: number; start: number; end: number; text: string; source: string; status: string }[]>;

function idleStatus() {
  return { state: "idle", meetingId: null, runId: null, cursorSeconds: 0, segmentCount: 0, provisionalCount: 0, reviewWindows: 0, errorCode: null, captureStatus: null, backlogSeconds: null };
}

beforeEach(() => {
  recordingState = "idle"; meetingId = null; failLiveStart = false; liveStatus = idleStatus();
  runLists = {}; words = {};
  useUIStore.setState({ language: "en", theme: "dark" });
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    switch (operation) {
      case "recording.devices": return { system: [{ id: "speaker", name: "Speaker" }], microphone: [{ id: "mic", name: "Mic" }] };
      case "recording.incomplete": return { meetings: [] };
      case "recording.snapshot": return { state: recordingState, meetingId, seconds: 3, error: null, skippedChunks: 0, levels: { system: 0, microphone: 0 } };
      case "recording.start": recordingState = "recording"; meetingId = meetingA; return { meetingId };
      case "recording.stop": recordingState = "completed"; return { state: recordingState };
      case "model.catalog": return { installed: [{ id: modelId, repository: "test/base" }], selectedId: modelId };
      case "live.start": {
        if (failLiveStart) throw new Error("live model failed");
        const id = String(params?.meetingId);
        liveStatus = { ...idleStatus(), state: "running", meetingId: id, runId: runA, captureStatus: "writing", backlogSeconds: 12 };
        runLists[id] = [{ runId: runA, state: "running" }];
        return { runId: runA };
      }
      case "live.status": return { ...liveStatus };
      case "live.runs": return { runs: runLists[String(params?.meetingId)] || [], nextCursor: null };
      case "live.read": return { items: words[String(params?.runId)] || [], nextCursor: null };
      case "live.cancel": liveStatus = { ...liveStatus, state: "cancelled" }; return { accepted: true };
      case "live.resume": liveStatus = { ...idleStatus(), state: "running", meetingId: String(params?.meetingId), runId: String(params?.runId) }; return { runId: params?.runId };
      default: throw new Error(`Unexpected operation ${operation}`);
    }
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("keeps live transcription off unless the user opts in", async () => {
  const user = userEvent.setup();
  render(<Recorder backendReady />);
  const toggle = await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }) as HTMLInputElement;
  expect(toggle.checked).toBe(false);
  await waitFor(() => expect((screen.getByRole("button", { name: "Record" }) as HTMLButtonElement).disabled).toBe(false));
  await user.click(screen.getByRole("button", { name: "Record" }));
  await screen.findByRole("button", { name: "Stop" });
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "live.start")).toBe(false);
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "model.catalog")).toBe(false);
});

it("still records when no local speech model is installed", async () => {
  const user = userEvent.setup();
  const normalCall = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation((operation, params) => {
    if (operation === "model.catalog") return Promise.resolve({ installed: [], selectedId: null }) as never;
    return normalCall(operation, params);
  });
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  expect(await screen.findByText("Install a speech model in Models to use live transcription.")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Record" }));
  expect(await screen.findByRole("button", { name: "Stop" })).toBeTruthy();
  expect(await screen.findByText("Choose an installed speech model to start live transcription. Recording continues.")).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "live.start" || op === "recording.stop")).toBe(false);
});

it("starts the chosen local model after recording succeeds", async () => {
  const user = userEvent.setup();
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  await waitFor(() => expect((screen.getByLabelText("Speech model for live transcription") as HTMLSelectElement).value).toBe(modelId));
  await user.click(screen.getByRole("button", { name: "Record" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([op, params]) =>
    op === "live.start" && params?.meetingId === meetingA && params?.modelId === modelId && params?.language === "vi")).toBe(true));
  const calls = vi.mocked(bridgeCall).mock.calls.map(([op]) => op);
  expect(calls.indexOf("recording.start")).toBeLessThan(calls.indexOf("live.start"));
  expect(await screen.findByText("Live transcription running")).toBeTruthy();
  expect(screen.getByText("Approx. 00:00:12 awaiting transcription")).toBeTruthy();
  expect(screen.getByText("Words may be missing or repeated. This is not a finished transcript or meeting minutes.")).toBeTruthy();
});

it("sends the selected language and explains per-window auto detection", async () => {
  const user = userEvent.setup();
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  await waitFor(() => expect((screen.getByLabelText("Speech model for live transcription") as HTMLSelectElement).value).toBe(modelId));
  await user.selectOptions(screen.getByLabelText("Live transcription language"), "auto");
  expect(screen.getByText("Language is detected separately for each window and may change between windows.")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Record" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([op, params]) =>
    op === "live.start" && params?.meetingId === meetingA && params?.language === "auto")).toBe(true));
});

it("keeps recording active when starting live transcription fails", async () => {
  const user = userEvent.setup();
  failLiveStart = true;
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  await waitFor(() => expect((screen.getByLabelText("Speech model for live transcription") as HTMLSelectElement).value).toBe(modelId));
  await user.click(screen.getByRole("button", { name: "Record" }));
  expect(await screen.findByText("Could not start live transcription. Check the speech model or wait for other AI and transcription tasks. Recording continues.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "recording.stop")).toBe(false);
  await user.click(screen.getByRole("button", { name: "Stop" }));
  expect(vi.mocked(bridgeCall).mock.calls.filter(([op]) => op === "recording.stop")).toHaveLength(1);
});

it("explains an active AI or transcription task and keeps recording", async () => {
  const user = userEvent.setup();
  const normalCall = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation((operation, params) => {
    if (operation === "live.start") return Promise.reject("RESOURCE_BUSY");
    return normalCall(operation, params);
  });
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  await waitFor(() => expect((screen.getByLabelText("Speech model for live transcription") as HTMLSelectElement).value).toBe(modelId));
  await user.click(screen.getByRole("button", { name: "Record" }));
  expect(await screen.findByText("Wait for the current transcription or AI job to finish. Recording continues.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "recording.stop")).toBe(false);
});

it("shows the latest words in time order with source and tentative labels", async () => {
  const user = userEvent.setup();
  recordingState = "recording"; meetingId = meetingA;
  liveStatus = { ...idleStatus(), state: "running", meetingId: meetingA, runId: runA, provisionalCount: 1, reviewWindows: 1 };
  runLists[meetingA] = [{ runId: runA, state: "running" }];
  words[runA] = [
    { id: 1, start: 8, end: 9, text: "Later words", source: "microphone", status: "provisional" },
    { id: 2, start: 2, end: 3, text: "Earlier words", source: "system", status: "committed" },
  ];
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  expect(await screen.findByText("Some words need review against the recording.")).toBeTruthy();
  const list = (await screen.findByText("Earlier words")).closest("ol")!;
  const entries = within(list).getAllByRole("listitem");
  expect(entries[0].textContent).toContain("Earlier words");
  expect(entries[0].textContent).toContain("System audio");
  expect(entries[1].textContent).toContain("Microphone");
  expect(entries[1].textContent).toContain("Tentative");
  await user.click(screen.getByRole("button", { name: "Stop live transcription" }));
  expect(vi.mocked(bridgeCall).mock.calls.some(([op, params]) => op === "live.cancel" && params?.meetingId === meetingA && params?.runId === runA)).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "recording.stop")).toBe(false);
});

it("ignores delayed words from a different meeting", async () => {
  const user = userEvent.setup();
  recordingState = "recording"; meetingId = meetingA;
  runLists[meetingA] = [{ runId: runA, state: "cancelled" }];
  runLists[meetingB] = [{ runId: runB, state: "cancelled" }];
  words[runB] = [{ id: 9, start: 1, end: 2, text: "New meeting words", source: "system", status: "committed" }];
  let releaseOld!: (value: unknown) => void;
  const oldPage = new Promise((resolve) => { releaseOld = resolve; });
  const normalCall = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation((operation, params) => {
    if (operation === "live.read" && params?.meetingId === meetingA) return oldPage as never;
    return normalCall(operation, params);
  });
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([op, params]) => op === "live.read" && params?.meetingId === meetingA)).toBe(true));
  meetingId = meetingB;
  expect(await screen.findByText("New meeting words", {}, { timeout: 4000 })).toBeTruthy();
  await act(async () => { releaseOld({ items: [{ id: 1, start: 1, end: 2, text: "Old meeting words", source: "system", status: "provisional" }], nextCursor: null }); });
  expect(screen.queryByText("Old meeting words")).toBeNull();
  expect(screen.getByText("New meeting words")).toBeTruthy();
});

it("resumes only a safe checkpoint for the current meeting", async () => {
  const user = userEvent.setup();
  recordingState = "completed"; meetingId = meetingA;
  runLists[meetingA] = [{ runId: runA, state: "cancelled" }];
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  const resume = await screen.findByRole("button", { name: "Resume live progress" });
  await user.click(resume);
  expect(vi.mocked(bridgeCall).mock.calls.some(([op, params]) => op === "live.resume" && params?.meetingId === meetingA && params?.runId === runA)).toBe(true);
});

it("explains when another task prevents resuming", async () => {
  const user = userEvent.setup();
  recordingState = "completed"; meetingId = meetingA;
  liveStatus = { ...idleStatus(), state: "error", meetingId: meetingA, runId: runA, errorCode: "cuda_cublas" };
  runLists[meetingA] = [{ runId: runA, state: "error", errorCode: "cuda_cublas" }];
  const normalCall = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation((operation, params) => {
    if (operation === "live.resume") return Promise.reject({ code: "RESOURCE_BUSY" });
    return normalCall(operation, params);
  });
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  await user.click(await screen.findByRole("button", { name: "Resume live progress" }));
  expect(await screen.findByText("Wait for the current transcription or AI job to finish.")).toBeTruthy();
});

it("explains an audio gap without offering unsafe resume", async () => {
  const user = userEvent.setup();
  recordingState = "completed"; meetingId = meetingA;
  liveStatus = { ...idleStatus(), state: "error", meetingId: meetingA, runId: runA, errorCode: "live_audio_gap" };
  runLists[meetingA] = [{ runId: runA, state: "error", errorCode: "live_audio_gap" }];
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  expect((await screen.findAllByText("Audio has a gap. Review or recover the recording before retrying.")).length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: "Resume live progress" })).toBeNull();
});

it.each([
  ["cuda_cublas", "CUDA could not load cuBLAS (cublas64_12.dll) or a required dependency."],
  ["cuda_cudnn", "CUDA could not load cuDNN (cudnn64_9.dll) or a required dependency."],
])("shows the specific CUDA library error %s", async (code, message) => {
  const user = userEvent.setup();
  recordingState = "completed"; meetingId = meetingA;
  liveStatus = { ...idleStatus(), state: "error", meetingId: meetingA, runId: runA, errorCode: code };
  runLists[meetingA] = [{ runId: runA, state: "error", errorCode: code }];
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Start live transcription when recording begins (experimental)" }));
  expect((await screen.findAllByText(message)).length).toBeGreaterThan(0);
  expect(await screen.findByRole("button", { name: "Resume live progress" })).toBeTruthy();
});

it("shows the CUDA library error in Vietnamese", async () => {
  const user = userEvent.setup();
  useUIStore.setState({ language: "vi" });
  recordingState = "completed"; meetingId = meetingA;
  liveStatus = { ...idleStatus(), state: "error", meetingId: meetingA, runId: runA, errorCode: "cuda_cublas" };
  runLists[meetingA] = [{ runId: runA, state: "error", errorCode: "cuda_cublas" }];
  render(<Recorder backendReady />);
  await user.click(await screen.findByRole("checkbox", { name: "Phiên âm khi bắt đầu ghi âm (thử nghiệm)" }));
  expect((await screen.findAllByText("CUDA không tải được cuBLAS (cublas64_12.dll) hoặc thư viện phụ thuộc.")).length).toBeGreaterThan(0);
});
