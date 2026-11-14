// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Models } from "@/features/models/Models";
import { Settings } from "@/features/settings/Settings";
import { bridgeCall } from "@/shared/bridge/client";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("uses an installed model while offline without starting a download", async () => {
  const user = userEvent.setup();
  let selectedId = "one";
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "model.catalog") return { choices: [], installed: [
      { id: "one", repository: "test/one", publisher: "test", license: "MIT", revision: "a", bytes: 100 },
      { id: "two", repository: "test/two", publisher: "test", license: "MIT", revision: "b", bytes: 100 },
    ], selectedId };
    if (operation === "model.installStatus") return { jobId: null, state: "idle", stage: "", progress: null, modelId: null, error: null };
    if (operation === "model.select") { selectedId = String(params?.modelId); return { selectedId }; }
    throw new Error(`Unexpected operation ${operation}`);
  });
  render(<Models backendReady />);
  await screen.findByText("test/two", { exact: true });
  await user.click(screen.getByRole("button", { name: "Use model" }));
  await waitFor(() => expect(selectedId).toBe("two"));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "model.install")).toBe(false);
});

it("shows redacted provider profiles and clears a newly entered key after save", async () => {
  const user = userEvent.setup();
  const profile = { id: "p".repeat(32), name: "Local provider", base_url: "http://localhost:1234/v1",
    model_id: "model", timeout_seconds: 30, hasKey: true };
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "provider.list") return { profiles: [profile] };
    if (operation === "provider.save") {
      expect(params?.apiKey).toBe("new-secret");
      return { profile };
    }
    throw new Error(`Unexpected operation ${operation}`);
  });
  render(<Settings backendReady />);
  await screen.findByText("Local provider");
  await user.click(screen.getByRole("button", { name: /^Local provider/ }));
  expect(screen.getByLabelText(/API key/).getAttribute("value")).toBe("");
  await user.type(screen.getByLabelText(/API key/), "new-secret");
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  await waitFor(() => expect(screen.getByLabelText(/API key/).getAttribute("value")).toBe(""));
  expect(document.body.textContent).not.toContain("new-secret");
});
