// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Reports } from "@/features/reports/Reports";
import { bridgeCall, importReportFile } from "@/shared/bridge/client";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn(), importReportFile: vi.fn(), exportReport: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("adds a native file and a saved transcript before starting the selected local model", async () => {
  let files: { id: string; name: string }[] = [];
  vi.mocked(bridgeCall).mockImplementation(async (op) => {
    if (op === "report.models") return { models: [
      { id: "qwen3.5:2b-q4_K_M", installed: true },
      { id: "qwen3:4b-instruct-2507-q4_K_M", installed: true },
      { id: "qwen3.5:4b-q4_K_M", installed: true },
    ] };
    if (op === "meeting.list") return { meetings: [{ id: "meeting1", name: "Project meeting" }] };
    if (op === "report.status") return { report: { state: "idle", detail: "", progress: 0, files, preview: "", facts: 0, warnings: 0, metrics: {} } };
    if (op === "report.addTranscript") { files = [...files, { id: "2", name: "Transcript: Project meeting" }]; return {}; }
    if (op === "report.start") return { started: true };
    throw new Error(`Unexpected operation: ${op}`);
  });
  vi.mocked(importReportFile).mockImplementation(async () => { files = [{ id: "1", name: "report.pdf" }]; return {}; });
  const user = userEvent.setup();
  render(<Reports backendReady />);
  await screen.findByText("Project meeting");
  expect(screen.getByText(/Fast and lightweight/)).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Local report model"), "qwen3:4b-instruct-2507-q4_K_M");
  expect(screen.getByText(/Suggested to try for the main report/)).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Local report model"), "qwen3.5:2b-q4_K_M");
  await user.click(screen.getByRole("button", { name: "Add document" }));
  expect(await screen.findByText("report.pdf")).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Add a saved meeting transcript"), "meeting1");
  await user.click(screen.getByRole("button", { name: "Add transcript" }));
  expect(await screen.findByText("Transcript: Project meeting")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Create report" }));
  await waitFor(() => expect(vi.mocked(bridgeCall)).toHaveBeenCalledWith("report.start", { model: "qwen3.5:2b-q4_K_M", form: "" }));
});
