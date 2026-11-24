// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Meetings } from "@/features/meetings/Meetings";
import { bridgeCall, demoAudioAvailable, importAudio, importDemoAudio } from "@/shared/bridge/client";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn(), demoAudioAvailable: vi.fn(), importAudio: vi.fn(), importDemoAudio: vi.fn() }));
vi.mock("@/features/meetings/AudioPlayer", () => ({ AudioPlayer: ({ meetingId, seekTo }: { meetingId: string; seekTo: { seconds: number } | null }) =>
  <div>Player {meetingId} {seekTo?.seconds ?? ""}</div> }));
vi.mock("@/features/transcript/TranscriptPanel", () => ({ TranscriptPanel: ({ onSeek }: { onSeek: (seconds: number) => void }) =>
  <button onClick={() => onSeek(12)}>Seek transcript source</button> }));
vi.mock("@/features/minutes/MinutesPanel", () => ({ MinutesPanel: ({ onOpenSource, onDirtyChange }: { onOpenSource: (run: string, seconds: number) => void; onDirtyChange: (dirty: boolean) => void }) => {
  const [draft, setDraft] = useState("");
  return <><button onClick={() => onOpenSource("r".repeat(32), 21)}>Open minutes source</button>
    <textarea aria-label="Minutes draft" value={draft} onChange={(event) => { setDraft(event.target.value); onDirtyChange(!!event.target.value); }} /></>;
} }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

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
