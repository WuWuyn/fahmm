// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Models } from "@/features/models/Models";
import { bridgeCall } from "@/shared/bridge/client";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("offers Qwen3 4B Instruct for local minutes and starts its download", async () => {
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "model.catalog") return { choices: [], installed: [], selectedId: null };
    if (operation === "model.installStatus") return { jobId: null, state: "idle", stage: "", progress: null, modelId: null, error: null };
    if (operation === "llm.availability") return { connected: true, models: [], selectedModel: "qwen3:4b-instruct", ready: false };
    if (operation === "llm.pullStatus") return { state: "idle", progress: 0, error: null, versionId: null };
    if (operation === "llm.pullStart") return { started: true };
    throw new Error(`Unexpected operation ${operation}`);
  });
  const user = userEvent.setup();
  render(<Models backendReady />);
  const comparison = screen.getByRole("table", { name: "Report model measurements from the earlier trial" });
  expect(within(comparison).getByText("9.67 tokens/sec")).toBeTruthy();
  expect(within(comparison).getByText("5.67 tokens/sec")).toBeTruthy();
  expect(within(comparison).getByText("4.77 tokens/sec")).toBeTruthy();
  expect(screen.getByText(/six documents were skipped for low RAM/)).toBeTruthy();
  expect(await screen.findByRole("heading", { name: "Local AI for meeting minutes" })).toBeTruthy();
  expect(screen.getByText(/qwen3:4b-instruct.*2.5 GB/)).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Download" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "llm.pullStart")).toBe(true));
});
