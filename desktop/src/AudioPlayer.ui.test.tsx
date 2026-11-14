// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { AudioPlayer } from "@/features/meetings/AudioPlayer";
import { bridgeCall } from "@/shared/bridge/client";

const wave = vi.hoisted(() => ({
  load: vi.fn(async () => undefined), on: vi.fn(), setTime: vi.fn(),
  playPause: vi.fn(), setOptions: vi.fn(), destroy: vi.fn(),
}));
vi.mock("wavesurfer.js", () => ({ default: { create: vi.fn(() => wave) } }));
vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("renders bounded peaks and seeks in a long recording through the media ticket", async () => {
  const meetingId = "a".repeat(32);
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "media.ticket") return { ticket: "ticket123", contentType: "audio/wav" };
    if (operation === "media.peaks") return { seconds: 3900, peaks: Array(1024).fill(0.2) };
    throw new Error(`Unexpected operation ${operation}`);
  });
  const view = render(<AudioPlayer meetingId={meetingId} seekTo={null} />);
  await waitFor(() => expect(wave.load).toHaveBeenCalled());
  const [url, peaks, duration] = wave.load.mock.calls[0] as unknown as [string, Float32Array[], number];
  expect(url).toBe(`http://fahmm.localhost/media/${meetingId}/ticket123`);
  expect(peaks[0]).toHaveLength(2048);
  expect(duration).toBe(3900);
  expect(screen.getByText(/65:00/)).toBeTruthy();
  view.rerender(<AudioPlayer meetingId={meetingId} seekTo={{ seconds: 3000, nonce: 1 }} />);
  await waitFor(() => expect(wave.setTime).toHaveBeenCalledWith(3000));
  expect(vi.mocked(bridgeCall).mock.calls.every(([operation]) => operation !== "media.resolve")).toBe(true);
});
