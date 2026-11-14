// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "@/app/App";
import { bridgeCall, bridgeStatus } from "@/shared/bridge/client";
import { useUIStore } from "@/shared/uiStore";

vi.mock("@/shared/bridge/client", () => ({
  bridgeCall: vi.fn(), bridgeStatus: vi.fn(), restartBridge: vi.fn(),
  importAudio: vi.fn(), exportSaved: vi.fn(),
}));

let recordingState = "idle";
beforeEach(() => {
  recordingState = "idle";
  localStorage.clear();
  window.location.hash = "#/recorder";
  useUIStore.setState({ theme: "dark", sidebarCollapsed: false });
  vi.mocked(bridgeStatus).mockResolvedValue(true);
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    switch (operation) {
      case "recording.devices": return { system: [{ id: "speaker", name: "Speaker" }], microphone: [{ id: "mic", name: "Microphone" }] };
      case "recording.incomplete": return { meetings: [] };
      case "recording.snapshot": return { state: recordingState, seconds: 1, meetingId: recordingState === "idle" ? null : "a".repeat(32), error: null, skippedChunks: 0 };
      case "recording.start": recordingState = "recording"; return { meetingId: "a".repeat(32) };
      case "recording.pause": recordingState = "paused"; return { state: recordingState };
      case "recording.resume": recordingState = "recording"; return { state: recordingState };
      case "recording.stop": recordingState = "completed"; return { state: recordingState };
      default: throw new Error(`Unexpected operation ${operation}`);
    }
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("desktop app shell", () => {
  it("persists a readable theme and keeps navigation keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "Record" });
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeTruthy();
    expect(screen.getAllByText("Local Only").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("fahmm-theme")).toBe("light");
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("link", { name: "Meetings" })).toBeTruthy();
    await user.tab();
    expect(document.activeElement).not.toBe(document.body);
  });

  it("runs Record, Pause, Resume, Stop through the bridge", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Record" }).hasAttribute("disabled")).toBe(false));
    await user.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByRole("button", { name: "Pause" });
    await user.click(screen.getByRole("button", { name: "Pause" }));
    await screen.findByRole("button", { name: "Resume" });
    await user.click(screen.getByRole("button", { name: "Resume" }));
    await screen.findByRole("button", { name: "Stop" });
    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(screen.getByText("Saved")).toBeTruthy());
    expect(vi.mocked(bridgeCall).mock.calls.map(([operation]) => operation)).toEqual(expect.arrayContaining([
      "recording.start", "recording.pause", "recording.resume", "recording.stop",
    ]));
  });

  it("offers recovery for an interrupted local recording", async () => {
    const user = userEvent.setup();
    vi.mocked(bridgeCall).mockImplementation(async (operation) => {
      switch (operation) {
        case "recording.devices": return { system: [], microphone: [] };
        case "recording.snapshot": return { state: "idle", seconds: 0, meetingId: null, error: null, skippedChunks: 0 };
        case "recording.incomplete": return { meetings: [{ id: "a".repeat(32), name: "Recovered meeting", createdAt: "2026-11-14T00:00:00Z" }] };
        case "recording.recover": return { state: "finalizing" };
        default: throw new Error(`Unexpected operation ${operation}`);
      }
    });
    render(<App />);
    await screen.findByText("Recovered meeting");
    await user.click(screen.getByRole("button", { name: "Recover" }));
    expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
      operation === "recording.recover" && params?.meetingId === "a".repeat(32))).toBe(true);
  });
});
