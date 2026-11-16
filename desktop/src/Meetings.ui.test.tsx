// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Meetings } from "@/features/meetings/Meetings";
import { bridgeCall, importAudio } from "@/shared/bridge/client";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn(), importAudio: vi.fn() }));
vi.mock("@/features/meetings/AudioPlayer", () => ({ AudioPlayer: ({ meetingId, seekTo }: { meetingId: string; seekTo: { seconds: number } | null }) =>
  <div>Player {meetingId} {seekTo?.seconds ?? ""}</div> }));
vi.mock("@/features/transcript/TranscriptPanel", () => ({ TranscriptPanel: ({ onSeek }: { onSeek: (seconds: number) => void }) =>
  <button onClick={() => onSeek(12)}>Seek transcript source</button> }));
vi.mock("@/features/minutes/MinutesPanel", () => ({ MinutesPanel: ({ onOpenSource }: { onOpenSource: (run: string, seconds: number) => void }) =>
  <button onClick={() => onOpenSource("r".repeat(32), 21)}>Open minutes source</button> }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("opens an existing offline meeting, imports audio, and navigates to saved source without a path", async () => {
  const user = userEvent.setup();
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
