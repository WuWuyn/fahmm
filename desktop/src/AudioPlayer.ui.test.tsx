// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AudioPlayer } from "@/features/meetings/AudioPlayer";
import { bridgeCall } from "@/shared/bridge/client";

const wave = vi.hoisted(() => ({
  load: vi.fn(async () => undefined), on: vi.fn(), setTime: vi.fn(),
  playPause: vi.fn(), play: vi.fn(async () => undefined), setOptions: vi.fn(),
  setPlaybackRate: vi.fn(), setMuted: vi.fn(), destroy: vi.fn(),
}));
vi.mock("wavesurfer.js", () => ({ default: { create: vi.fn(() => wave) } }));
vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("renders bounded peaks and seeks in a long recording through the media ticket", async () => {
  const user = userEvent.setup();
  const meetingId = "a".repeat(32);
  const positions: number[] = [];
  const durations: number[] = [];
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "media.ticket") return { ticket: "ticket123", contentType: "audio/wav" };
    if (operation === "media.peaks") return { seconds: 3900, peaks: Array(1024).fill(0.2) };
    throw new Error(`Unexpected operation ${operation}`);
  });
  const view = render(<AudioPlayer meetingId={meetingId} seekTo={null}
    onPositionChange={(seconds) => positions.push(seconds)} onDurationChange={(seconds) => durations.push(seconds)} />);
  await waitFor(() => expect(wave.load).toHaveBeenCalled());
  const [url, peaks, duration] = wave.load.mock.calls[0] as unknown as [string, Float32Array[], number];
  expect(url).toBe(`http://fahmm.localhost/media/${meetingId}/ticket123`);
  expect(peaks[0]).toHaveLength(2048);
  expect(duration).toBe(3900);
  expect(durations).toContain(3900);
  const timeHandler = wave.on.mock.calls.find(([event]) => event === "timeupdate")?.[1] as (seconds: number) => void;
  act(() => timeHandler(12.8));
  expect(positions).toContain(12.8);
  expect(screen.getByText("00:12 / 65:00")).toBeTruthy();
  await user.selectOptions(screen.getByRole("combobox", { name: "Playback speed" }), "1.5");
  expect(wave.setPlaybackRate).toHaveBeenCalledWith(1.5);
  await user.click(screen.getByRole("button", { name: "Mute audio" }));
  expect(wave.setMuted).toHaveBeenCalledWith(true);
  view.rerender(<AudioPlayer meetingId={meetingId} seekTo={{ seconds: 3000, nonce: 1, play: true }}
    onPositionChange={(seconds) => positions.push(seconds)} onDurationChange={(seconds) => durations.push(seconds)} />);
  await waitFor(() => expect(wave.setTime).toHaveBeenCalledWith(3000));
  expect(wave.play).toHaveBeenCalled();
  expect(vi.mocked(bridgeCall).mock.calls.every(([operation]) => operation !== "media.resolve")).toBe(true);
});
