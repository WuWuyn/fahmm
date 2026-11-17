// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MinutesPanel } from "@/features/minutes/MinutesPanel";
import { bridgeCall, exportSaved } from "@/shared/bridge/client";
import { useUIStore } from "@/shared/uiStore";

vi.mock("@/shared/bridge/client", () => ({ bridgeCall: vi.fn(), exportSaved: vi.fn() }));

let versionId: string | null;
let previewCount: number;
let minutesOrigin: string;
let sourceOrigin: string | null;
let domainMode: boolean;
let extraVersionId: string | null;
beforeEach(() => {
  versionId = null; previewCount = 0; minutesOrigin = "extractive"; sourceOrigin = "extractive";
  domainMode = false; extraVersionId = null;
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    switch (operation) {
      case "minutes.list": return { versions: [versionId, extraVersionId].filter(Boolean).map((id) => ({ version_id: id, created_at: "2026-11-14T00:00:00Z", review_state: "unverified", origin: minutesOrigin, source_origin: sourceOrigin })), activeVersionId: versionId };
      case "minutes.read": return { version: { manifest: { version_id: versionId, run_id: "r".repeat(32), created_at: "2026-11-14T00:00:00Z", review_state: "unverified", origin: minutesOrigin, source_origin: sourceOrigin }, content: domainMode ? {
        domain_schema_version: 1, domain: { meeting_type: "general", metadata: {
          title: { value: "Client call", provenance: "user_provided", sources: [] },
          meeting_datetime: { value: null, provenance: "unknown", sources: [] },
          project_customer: { value: null, provenance: "unknown", sources: [] },
          participants: { value: [], provenance: "unknown", sources: [] },
          objective: { value: null, provenance: "unknown", sources: [] },
        }, sections: { topics: [{ item_id: "a".repeat(32), text: "Review API", origin: "extractive",
          review_status: "needs_review", sources: [{ run_id: "r".repeat(32), segment_id: 1, start: 0, end: 1, excerpt: "Review API" }] }] } },
      } : { user_text: "# Bản nháp", actions: [] } } };
      case "minutes.renderBody": return { markdown: "# Bản nháp" };
      case "minutes.sourceDrift": return { sources: domainMode ? [{ location: `sections.topics.${"a".repeat(32)}`,
        source: { run_id: "r".repeat(32), segment_id: 1, start: 0, end: 1, excerpt: "Review API" },
        current_text: "Changed API", drifted: true }] : [] };
      case "minutes.select": return { activeVersionId: extraVersionId };
      case "minutes.template": return { template: { headings: { title: "Tiêu đề" }, guidance: "Review sources", topic_limit: 5 } };
      case "provider.list": return { profiles: [{ id: "p".repeat(32), name: "Provider", model_id: "model", hasKey: false }] };
      case "transcript.list": return { activeRunId: "r".repeat(32) };
      case "transcript.read": return { run: { working: [{ id: 1, start: 0, end: 1, text: "Xin chào" }] } };
      case "minutes.generateOffline": versionId = "m".repeat(32); return { versionId };
      case "minutes.setType": versionId = "t".repeat(32); return { versionId };
      case "cloud.preview": previewCount += 1; return { previewId: `preview-${previewCount}`, preview: {
        destination_hostname: "example.org", warning: "Content leaves this device", transcript: "Xin chào",
        prompt: "Viết biên bản", token_limit: 2000, request_body: { model: "model", messages: [{ content: "Xin chào" }] },
      } };
      case "cloud.cancel": return { cancelled: true };
      case "cloud.confirm": return { confirmed: true };
      case "cloud.send": versionId = "c".repeat(32); return { versionId };
      default: throw new Error(`Unexpected operation ${operation}`);
    }
  });
});
afterEach(() => { cleanup(); useUIStore.setState({ language: "en" }); vi.clearAllMocks(); vi.unstubAllGlobals(); });

it("shows draft provenance and action caveat for edited Markdown without structured actions", async () => {
  versionId = "m".repeat(32);
  minutesOrigin = "user_edit";
  sourceOrigin = "extractive";
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByText("Edited from an offline extractive draft; user edits have not been automatically verified.")).toBeTruthy();
  expect(screen.getByText("Any action items in these minutes are suggestions, not assigned or tracked tasks.")).toBeTruthy();
});

it("keeps Restricted meetings offline and labels drafts unverified", async () => {
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await screen.findByRole("button", { name: "Create offline draft" });
  expect(screen.getByLabelText("Meeting type").closest(".minutes-create")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Create offline draft" }));
  await waitFor(() => expect(screen.getByText("Unverified")).toBeTruthy());
  expect(screen.getByRole("button", { name: "Preview provider payload" }).hasAttribute("disabled")).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "cloud.preview")).toBe(false);
});

it("shows the new draft controls and review state in Vietnamese", async () => {
  versionId = "m".repeat(32);
  useUIStore.setState({ language: "vi" });
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByRole("heading", { name: "Tạo bản nháp mới" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Tạo bản nháp ngoại tuyến" })).toBeTruthy();
  await waitFor(() => expect(document.querySelector(".review-badge")?.textContent).toBe("Chưa xác minh"));
});

it("uses the selected type for the next draft until the user applies it to a saved version", async () => {
  domainMode = true; versionId = "m".repeat(32);
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await screen.findByText("Review API");
  await user.selectOptions(screen.getByLabelText("Meeting type"), "requirement_gathering");
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.setType")).toBe(false);
  expect(screen.getByText("This type will be used for the next draft.")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Apply type to saved version" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
    operation === "minutes.setType" && params?.meetingType === "requirement_gathering")).toBe(true));
});

it("cancels a preview and requires a fresh confirmation for the next send", async () => {
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="cloud_permitted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await screen.findByText(/0\.0s · Xin chào/);
  const boxes = screen.getAllByRole("checkbox");
  await user.click(boxes[0]); await user.click(boxes[1]);
  await user.click(screen.getByRole("button", { name: "Preview provider payload" }));
  await screen.findByRole("dialog", { name: "Review provider send" });
  expect(screen.getByText(/Exact request body/)).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "cloud.send")).toBe(false);
  await user.click(screen.getByRole("button", { name: "Preview provider payload" }));
  await user.click(screen.getByRole("button", { name: "Confirm and send" }));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
    operation === "cloud.send" && params?.previewId === "preview-2")).toBe(true));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
    operation === "cloud.cancel" && params?.previewId === "preview-1")).toBe(true);
});

it("copies the saved Markdown only after warning about dirty edits", async () => {
  versionId = "m".repeat(32);
  const user = userEvent.setup();
  const copy = vi.fn(async () => undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: copy } });
  vi.stubGlobal("confirm", vi.fn(() => false));
  vi.mocked(bridgeCall).mockImplementationOnce(async () => ({
    versions: [{ version_id: versionId, created_at: "2026-11-14T00:00:00Z", review_state: "unverified", origin: "extractive" }],
    activeVersionId: versionId,
  }));
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await screen.findByRole("button", { name: "Edit" });
  await user.click(screen.getByRole("button", { name: "Edit" }));
  await user.clear(screen.getByRole("textbox", { name: "Edit minutes Markdown" }));
  await user.type(screen.getByRole("textbox", { name: "Edit minutes Markdown" }), "Unsaved text");
  await user.click(screen.getByRole("button", { name: "Copy Markdown" }));
  expect(copy).not.toHaveBeenCalled();
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "export.minutesMarkdown")).toBe(false);
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    if (operation === "export.minutesMarkdown") return { markdown: "Saved Markdown" };
    throw new Error(`Unexpected operation ${operation}`);
  });
  await user.click(screen.getByRole("button", { name: "Copy Markdown" }));
  await waitFor(() => expect(copy).toHaveBeenCalledWith("Saved Markdown"));
  expect(screen.queryByText("Unsaved edits")).toBeNull();
  expect(vi.mocked(exportSaved)).not.toHaveBeenCalled();
});

it("keeps a dirty domain draft when version switching is cancelled", async () => {
  domainMode = true; versionId = "m".repeat(32); extraVersionId = "n".repeat(32);
  const user = userEvent.setup();
  vi.stubGlobal("confirm", vi.fn(() => false));
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}}
    onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  await user.type(screen.getByRole("textbox", { name: "Objective" }), "Review rollout");
  await waitFor(() => expect(screen.getAllByText("Unsaved edits").length).toBeGreaterThan(0));
  await user.selectOptions(screen.getByLabelText("Saved version"), extraVersionId);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.select")).toBe(false);
  expect((screen.getByLabelText("Saved version") as HTMLSelectElement).value).toBe(versionId);
});
