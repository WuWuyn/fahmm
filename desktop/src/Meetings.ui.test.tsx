// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Meetings } from "@/features/meetings/Meetings";
import { bridgeCall, demoAudioAvailable, discardDroppedAudio, importAudio, importDemoAudio, importDroppedAudio, listenAudioDrag } from "@/shared/bridge/client";
import type { AudioDragEvent } from "@/shared/bridge/client";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn(), demoAudioAvailable: vi.fn(), importAudio: vi.fn(), importDemoAudio: vi.fn(),
  listenAudioDrag: vi.fn(async () => () => {}), importDroppedAudio: vi.fn(), discardDroppedAudio: vi.fn(async () => {}) }));
vi.mock("@/features/meetings/AudioPlayer", () => ({ AudioPlayer: ({ meetingId, seekTo }: { meetingId: string; seekTo: { seconds: number } | null }) =>
  <div>Player {meetingId} {seekTo?.seconds ?? ""}</div> }));
vi.mock("@/features/transcript/TranscriptPanel", () => ({ TranscriptPanel: ({ onSeek }: { onSeek: (seconds: number) => void }) =>
  <button onClick={() => onSeek(12)}>Seek transcript source</button> }));
vi.mock("@/features/minutes/MinutesPanel", () => ({ MinutesPanel: ({ onOpenSource, onDirtyChange }: { onOpenSource: (run: string, seconds: number) => void; onDirtyChange: (dirty: boolean) => void }) => {
  const [draft, setDraft] = useState("");
  return <><button onClick={() => onOpenSource("r".repeat(32), 21)}>Open minutes source</button>
    <textarea aria-label="Minutes draft" value={draft} onChange={(event) => { setDraft(event.target.value); onDirtyChange(!!event.target.value); }} /></>;
} }));
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

it("opens an existing offline meeting, imports audio, and navigates to saved source without a path", async () => {
  const user = userEvent.setup();
  vi.mocked(demoAudioAvailable).mockResolvedValue(false);
  const first = { id: "a".repeat(32), name: "Existing meeting", created_at: "2026-11-14T00:00:00Z",
    source_kind: "recorded", recording_state: "completed", processing_state: "completed", privacy_mode: "restricted" };
  const imported = { ...first, id: "b".repeat(32), name: "Imported audio", source_kind: "imported" };
  let meetings = [first];
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "meeting.list") return { meetings };
    if (operation === "meeting.cleanupList") return { deletions: [], imports: [] };
    if (operation === "transcript.select") return { activeRunId: "r".repeat(32) };
    throw new Error(`Unexpected operation ${operation}`);
  });
  vi.mocked(importAudio).mockImplementation(async () => { meetings = [first, imported]; return { meetingId: imported.id }; });
  render(<Meetings backendReady />);
  await screen.findByText("Existing meeting", { selector: "h2" });
  expect(screen.getByText(`Player ${first.id}`)).toBeTruthy();
  expect(screen.getAllByText("Local Only")).toHaveLength(1);
  expect(screen.getByText("Transcript ready")).toBeTruthy();
  const search = screen.getByRole("textbox", { name: "Search meetings" });
  await user.type(search, "not found");
  expect(screen.getByText("No meetings match your search.")).toBeTruthy();
  await user.clear(search);
  await user.click(screen.getByRole("button", { name: "More meeting actions" }));
  expect(await screen.findByRole("menuitem", { name: "Delete meeting" })).toBeTruthy();
  await user.keyboard("{Escape}");
  await user.click(screen.getByRole("button", { name: "Import audio" }));
  await screen.findByText("Imported audio", { selector: "h2" });
  expect(screen.getByText(`Player ${imported.id}`)).toBeTruthy();
  await user.click(screen.getByRole("tab", { name: "Minutes" }));
  await user.click(screen.getByRole("button", { name: "Open minutes source" }));
  await waitFor(() => expect(screen.getByRole("tab", { name: "Transcript" }).getAttribute("aria-selected")).toBe("true"));
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "transcript.select")).toBe(true);
  expect(document.body.textContent).not.toContain("C:\\");
});

it("offers the local 60-minute sample and opens its imported meeting", async () => {
  const user = userEvent.setup();
  const sample = { id: "c".repeat(32), name: "Họp mẫu — Yêu cầu hệ thống bán hàng (60 phút)",
    created_at: "2026-11-18T00:00:00Z", source_kind: "imported", recording_state: "completed",
    processing_state: "not_started", privacy_mode: "restricted" };
  let meetings: typeof sample[] = [];
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "meeting.list") return { meetings };
    if (operation === "meeting.cleanupList") return { deletions: [], imports: [] };
    throw new Error(`Unexpected operation ${operation}`);
  });
  vi.mocked(demoAudioAvailable).mockResolvedValue(true);
  vi.mocked(importDemoAudio).mockImplementation(async () => { meetings = [sample]; return { meetingId: sample.id }; });
  render(<Meetings backendReady />);
  expect(await screen.findByText("Sample meeting · 60 min")).toBeTruthy();
  await user.type(screen.getByRole("textbox", { name: "Search meetings" }), "unrelated");
  await user.click(screen.getByRole("button", { name: "Use sample recording" }));
  await screen.findByText(sample.name, { selector: "h2" });
  expect(screen.getByRole("textbox", { name: "Search meetings" })).toHaveProperty("value", "");
  expect(screen.getByText(`Player ${sample.id}`)).toBeTruthy();
  expect(vi.mocked(importDemoAudio)).toHaveBeenCalledOnce();
});


it("preserves minutes across tabs and protects them when opening a newly recorded meeting", async () => {
  const first = { id: "a".repeat(32), name: "First meeting", created_at: "2026-11-14T00:00:00Z",
    source_kind: "recorded", recording_state: "completed", processing_state: "completed", privacy_mode: "restricted" };
  const recorded = { ...first, id: "b".repeat(32), name: "New recording" };
  let meetings = [first];
  vi.mocked(demoAudioAvailable).mockResolvedValue(false);
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "meeting.list") return { meetings };
    if (operation === "meeting.cleanupList") return { deletions: [], imports: [] };
    throw new Error(`Unexpected operation ${operation}`);
  });
  const user = userEvent.setup();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const { rerender } = render(<Meetings backendReady visible />);
  await screen.findByText("First meeting", { selector: "h2" });
  await user.click(screen.getByRole("tab", { name: "Minutes" }));
  await user.type(screen.getByRole("textbox", { name: "Minutes draft" }), "Preserve this");
  await user.click(screen.getByRole("tab", { name: "Transcript" }));
  await user.click(screen.getByRole("tab", { name: "Minutes" }));
  expect(screen.getByRole("textbox", { name: "Minutes draft" })).toHaveProperty("value", "Preserve this");
  rerender(<Meetings backendReady visible={false} />);
  meetings = [first, recorded];
  rerender(<Meetings backendReady visible openMeetingId={recorded.id} />);
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(screen.getByText("First meeting", { selector: "h2" })).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "Minutes draft" })).toHaveProperty("value", "Preserve this");
  confirm.mockRestore();
});

it("imports only a native drop in the audio area, accounting for Windows scaling", async () => {
  let drag: ((event: AudioDragEvent) => void) | undefined;
  const stop = vi.fn();
  vi.mocked(listenAudioDrag).mockImplementation(async (handler) => { drag = handler; return stop; });
  vi.mocked(demoAudioAvailable).mockResolvedValue(false);
  const meeting = { id: "d".repeat(32), name: "Dropped meeting", created_at: "2026-11-14T00:00:00Z",
    source_kind: "imported", recording_state: "completed", processing_state: "not_started", privacy_mode: "restricted" };
  let meetings: typeof meeting[] = [];
  vi.mocked(bridgeCall).mockImplementation(async (op) => {
    if (op === "meeting.list") return { meetings };
    if (op === "meeting.cleanupList") return { deletions: [], imports: [] };
    throw new Error(`Unexpected operation ${op}`);
  });
  vi.mocked(importDroppedAudio).mockImplementation(async () => { meetings = [meeting]; return { meetingId: meeting.id }; });
  vi.stubGlobal("devicePixelRatio", 2);
  const view = render(<Meetings backendReady />);
  await waitFor(() => expect(drag).toBeDefined());
  const zone = screen.getByRole("region", { name: "Audio import drop area" });
  vi.spyOn(zone, "getBoundingClientRect").mockReturnValue({ left: 10, top: 20, right: 210, bottom: 120 } as DOMRect);
  act(() => drag!({ type: "enter", x: 40, y: 60 }));
  expect(screen.getByText("Release to import one audio file")).toBeTruthy();
  act(() => drag!({ type: "drop", x: 500, y: 500, token: 11 }));
  await waitFor(() => expect(discardDroppedAudio).toHaveBeenCalledWith(11));
  expect(importDroppedAudio).not.toHaveBeenCalled();
  act(() => drag!({ type: "drop", x: 40, y: 60, token: 12 }));
  await screen.findByText("Dropped meeting", { selector: "h2" });
  expect(importDroppedAudio).toHaveBeenCalledWith(12);
  expect(screen.getByText(`Player ${meeting.id}`)).toBeTruthy();
  view.unmount();
  expect(stop).toHaveBeenCalledOnce();
});

it("rejects invalid or multiple dropped files and preserves an unsaved draft when declined", async () => {
  let drag: ((event: AudioDragEvent) => void) | undefined;
  vi.mocked(listenAudioDrag).mockImplementation(async (handler) => { drag = handler; return () => {}; });
  vi.mocked(demoAudioAvailable).mockResolvedValue(false);
  const meeting = { id: "a".repeat(32), name: "Existing", created_at: "2026-11-14T00:00:00Z",
    source_kind: "recorded", recording_state: "completed", processing_state: "completed", privacy_mode: "restricted" };
  vi.mocked(bridgeCall).mockImplementation(async (op) => {
    if (op === "meeting.list") return { meetings: [meeting] };
    if (op === "meeting.cleanupList") return { deletions: [], imports: [] };
    throw new Error(`Unexpected operation ${op}`);
  });
  const user = userEvent.setup();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<Meetings backendReady />);
  await screen.findByText("Existing", { selector: "h2" });
  await waitFor(() => expect(drag).toBeDefined());
  const zone = screen.getByRole("region", { name: "Audio import drop area" });
  vi.spyOn(zone, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, right: 200, bottom: 200 } as DOMRect);
  act(() => drag!({ type: "drop", x: 50, y: 50, error: "multiple" }));
  expect(screen.getByRole("alert").textContent).toBe("Drop one audio file at a time.");
  act(() => drag!({ type: "drop", x: 50, y: 50, error: "unsupported" }));
  expect(screen.getByRole("alert").textContent).toContain("Unsupported file");
  await user.click(screen.getByRole("tab", { name: "Minutes" }));
  await user.type(screen.getByRole("textbox", { name: "Minutes draft" }), "Do not lose this");
  vi.mocked(importDroppedAudio).mockResolvedValue({ meetingId: "b".repeat(32) });
  act(() => drag!({ type: "drop", x: 50, y: 50, token: 22 }));
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(importDroppedAudio).toHaveBeenCalledWith(22);
  expect(screen.getByRole("textbox", { name: "Minutes draft" })).toHaveProperty("value", "Do not lose this");
  confirm.mockRestore();
});

it("does not discard edits made while a dropped file is importing", async () => {
  let drag: ((event: AudioDragEvent) => void) | undefined;
  let finishImport: ((result: { meetingId: string }) => void) | undefined;
  vi.mocked(listenAudioDrag).mockImplementation(async (handler) => { drag = handler; return () => {}; });
  vi.mocked(demoAudioAvailable).mockResolvedValue(false);
  const first = { id: "a".repeat(32), name: "Existing", created_at: "2026-11-14T00:00:00Z",
    source_kind: "recorded", recording_state: "completed", processing_state: "completed", privacy_mode: "restricted" };
  const imported = { ...first, id: "b".repeat(32), name: "Imported" };
  let meetings = [first];
  vi.mocked(bridgeCall).mockImplementation(async (op) => {
    if (op === "meeting.list") return { meetings };
    if (op === "meeting.cleanupList") return { deletions: [], imports: [] };
    throw new Error(`Unexpected operation ${op}`);
  });
  vi.mocked(importDroppedAudio).mockImplementation(() => new Promise((resolve) => { finishImport = resolve; }));
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const user = userEvent.setup();
  render(<Meetings backendReady />);
  await screen.findByText("Existing", { selector: "h2" });
  await waitFor(() => expect(drag).toBeDefined());
  vi.spyOn(screen.getByRole("region", { name: "Audio import drop area" }), "getBoundingClientRect")
    .mockReturnValue({ left: 0, top: 0, right: 200, bottom: 200 } as DOMRect);
  act(() => drag!({ type: "drop", x: 50, y: 50, token: 31 }));
  await waitFor(() => expect(finishImport).toBeDefined());
  act(() => drag!({ type: "drop", x: 50, y: 50, token: 32 }));
  await waitFor(() => expect(discardDroppedAudio).toHaveBeenCalledWith(32));
  await user.click(screen.getByRole("tab", { name: "Minutes" }));
  await user.type(screen.getByRole("textbox", { name: "Minutes draft" }), "New draft");
  meetings = [first, imported];
  await act(async () => finishImport!({ meetingId: imported.id }));
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(screen.getByText("Existing", { selector: "h2" })).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "Minutes draft" })).toHaveProperty("value", "New draft");
  expect(screen.getByRole("alert").textContent).toContain("Audio imported");
  confirm.mockRestore();
});

it("keeps the file picker available if native drag events cannot be registered", async () => {
  vi.mocked(listenAudioDrag).mockRejectedValueOnce(new Error("unavailable"));
  vi.mocked(demoAudioAvailable).mockResolvedValue(false);
  vi.mocked(bridgeCall).mockImplementation(async (op) => {
    if (op === "meeting.list") return { meetings: [] };
    if (op === "meeting.cleanupList") return { deletions: [], imports: [] };
    throw new Error(`Unexpected operation ${op}`);
  });
  vi.mocked(importAudio).mockResolvedValue({ cancelled: true });
  const user = userEvent.setup();
  render(<Meetings backendReady />);
  expect(await screen.findByText("Drag and drop unavailable. Use Import audio.")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Import audio" }));
  expect(importAudio).toHaveBeenCalledOnce();
});
