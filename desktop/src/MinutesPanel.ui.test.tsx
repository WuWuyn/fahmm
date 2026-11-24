// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
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
let activeTranscript: { id: number; start: number; end: number; text: string }[] | null;
let generationError: boolean;
let generationGate: Promise<void> | null;
let sourceDriftError: boolean;
let versionReadError: boolean;
let localAIReady: boolean;
let localAIError: boolean;
let localAIStarted: boolean;
beforeEach(() => {
  versionId = null; previewCount = 0; minutesOrigin = "extractive"; sourceOrigin = "extractive";
  domainMode = false; extraVersionId = null; activeTranscript = [{ id: 1, start: 0, end: 1, text: "Xin chào" }];
  generationError = false; generationGate = null; sourceDriftError = false; versionReadError = false; localAIReady = false; localAIError = false; localAIStarted = false;
  vi.mocked(bridgeCall).mockImplementation(async (operation) => {
    switch (operation) {
      case "minutes.list": return { versions: [versionId, extraVersionId].filter(Boolean).map((id) => ({ version_id: id, created_at: "2026-11-14T00:00:00Z", review_state: "unverified", origin: minutesOrigin, source_origin: sourceOrigin })), activeVersionId: versionId };
      case "minutes.read":
        if (versionReadError) throw new Error("UNSUPPORTED_OPERATION");
        return { version: { manifest: { version_id: versionId, run_id: "r".repeat(32), created_at: "2026-11-14T00:00:00Z", review_state: "unverified", origin: minutesOrigin, source_origin: sourceOrigin }, content: domainMode ? {
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
      case "minutes.sourceDrift":
        if (sourceDriftError) throw new Error("UNSUPPORTED_OPERATION");
        return { sources: domainMode ? [{ location: `sections.topics.${"a".repeat(32)}`,
        source: { run_id: "r".repeat(32), segment_id: 1, start: 0, end: 1, excerpt: "Review API" },
        current_text: "Changed API", drifted: true }] : [] };
      case "minutes.select": return { activeVersionId: extraVersionId };
      case "minutes.template": return { template: { headings: { title: "Tiêu đề" }, guidance: "Review sources", topic_limit: 5 } };
      case "provider.list": return { profiles: [{ id: "p".repeat(32), name: "Provider", model_id: "model", hasKey: false }] };
      case "llm.availability": return { connected: localAIReady, models: localAIReady ? ["qwen3:4b-instruct"] : [],
        selectedModel: "qwen3:4b-instruct", ready: localAIReady };
      case "minutes.generateLocalStart": localAIStarted = true; return { started: true, jobId: "j".repeat(32) };
      case "minutes.localCheckpoint": return { available: false, meetingType: null, progress: 0, error: null };
      case "minutes.localStatus":
        if (!localAIStarted) return { state: "idle", progress: 0, error: null, versionId: null, meetingId: null };
        if (localAIError) return { state: "failed", progress: 0, error: "Model failed", versionId: null };
        versionId = "l".repeat(32); minutesOrigin = "local_llm";
        return { state: "completed", progress: 1, error: null, versionId };
      case "transcript.list": return { activeRunId: activeTranscript ? "r".repeat(32) : null };
      case "transcript.read": return { run: { working: activeTranscript } };
      case "minutes.generateOffline":
        if (generationGate) await generationGate;
        if (generationError) throw new Error("Generation failed");
        versionId = "m".repeat(32); return { versionId };
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
  expect(await screen.findByText("Edited from locally extracted minutes.")).toBeTruthy();
  expect(screen.getByText("Any action items in these minutes are suggestions, not assigned or tracked tasks.")).toBeTruthy();
});

it("creates and displays minutes immediately while keeping Restricted meetings offline", async () => {
  const user = userEvent.setup();
  vi.mocked(exportSaved).mockResolvedValue({ saved: true, displayName: "minutes.md" });
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await screen.findByRole("button", { name: "Generate meeting minutes" });
  expect(screen.getByText("Advanced minutes options")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Generate meeting minutes" }));
  await waitFor(() => expect(screen.getByRole("article").textContent).toContain("Bản nháp"));
  expect(screen.queryByText("Unverified")).toBeNull();
  expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  expect(screen.getByRole("button", { name: "Export Word (.docx)" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Export MD" }));
  await waitFor(() => expect(vi.mocked(exportSaved)).toHaveBeenCalledWith(
    "a".repeat(32), "m".repeat(32), "minutes"));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
    operation === "minutes.generateOffline" && params?.meetingType === "general")).toBe(true);
  expect(screen.getByRole("button", { name: "Preview provider payload" }).hasAttribute("disabled")).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "cloud.preview")).toBe(false);
});

it("uses installed local AI for the one-click minutes action and labels its origin", async () => {
  localAIReady = true;
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByText(/Write the DENSO form with qwen3:4b-instruct/)).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Generate meeting minutes" }));
  await waitFor(() => expect(screen.getByText("Local Ollama wrote the DENSO form with transcript citations.")).toBeTruthy(),
    { timeout: 3000 });
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateLocalStart")).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateOffline")).toBe(false);
});

it("explains when another model task prevents starting AI minutes", async () => {
  localAIReady = true;
  const fallback = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "minutes.generateLocalStart") throw new Error("RESOURCE_BUSY");
    return fallback(operation, params);
  });
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await screen.findByText(/Write the DENSO form/);
  await user.click(screen.getByRole("button", { name: "Generate meeting minutes" }));
  expect(await screen.findByText("Wait for the current transcription or AI job to finish.")).toBeTruthy();
});

it("resumes saved AI progress and lets the user stop the running request", async () => {
  localAIReady = true;
  let resumed = false;
  let stopped = false;
  const fallback = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "minutes.localCheckpoint") return { available: true, meetingType: "general", progress: 0.35, error: null };
    if (operation === "minutes.resumeLocalStart") { resumed = true; return { started: true, jobId: "j".repeat(32) }; }
    if (operation === "minutes.cancelLocal") { stopped = true; return { accepted: true }; }
    if (operation === "minutes.localStatus") return {
      state: stopped ? "cancelled" : resumed ? "running" : "idle",
      progress: 0.35, error: null, versionId: null, meetingId: resumed ? "a".repeat(32) : null, jobId: resumed ? "j".repeat(32) : null,
    };
    return fallback(operation, params);
  });
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Resume AI generation" }));
  await user.click(await screen.findByRole("button", { name: "Stop AI generation" }));
  expect(await screen.findByText("AI generation stopped. Saved progress can be resumed.", {}, { timeout: 3000 })).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.resumeLocalStart")).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.cancelLocal")).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateOffline")).toBe(false);
});

it("ignores a late checkpoint response from a different meeting", async () => {
  localAIReady = true;
  let release!: (value: unknown) => void;
  const first = new Promise((resolve) => { release = resolve; });
  const fallback = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "minutes.localCheckpoint") {
      if (params?.meetingId === "a".repeat(32)) return first;
      return { available: false, meetingType: null, progress: 0, error: null };
    }
    return fallback(operation, params);
  });
  const panel = (meetingId: string) => <MinutesPanel meetingId={meetingId} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />;
  const { rerender } = render(panel("a".repeat(32)));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([op, params]) =>
    op === "minutes.localCheckpoint" && params?.meetingId === "a".repeat(32))).toBe(true));
  rerender(panel("b".repeat(32)));
  await waitFor(() => expect(vi.mocked(bridgeCall).mock.calls.some(([op, params]) =>
    op === "minutes.localCheckpoint" && params?.meetingId === "b".repeat(32))).toBe(true));
  await act(async () => {
    release({ available: true, meetingType: "general", progress: 0.5, error: null });
    await first;
  });
  expect(screen.queryByRole("button", { name: "Resume AI generation" })).toBeNull();
});

it("creates a source-linked extractive draft when local AI is available", async () => {
  localAIReady = true;
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Create fast extractive draft" }));
  expect(await screen.findByText("Extracted locally from the transcript; not a semantic AI summary.")).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation, params]) =>
    operation === "minutes.generateOffline" && params?.meetingType === "general")).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateLocalStart")).toBe(false);
});

it("keeps local AI errors visible without silently falling back", async () => {
  localAIReady = true; localAIError = true;
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await screen.findByRole("button", { name: "Create fast extractive draft" });
  await user.click(screen.getByRole("button", { name: "Generate meeting minutes" }));
  expect((await screen.findByRole("alert", {}, { timeout: 3000 })).textContent).toContain("Model failed");
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateOffline")).toBe(false);
  await user.click(screen.getByRole("button", { name: "Create fast extractive draft" }));
  expect(await screen.findByText("Extracted locally from the transcript; not a semantic AI summary.")).toBeTruthy();
});

it("disables the extractive action for blank text and while a draft is running", async () => {
  localAIReady = true;
  activeTranscript = [{ id: 1, start: 0, end: 1, text: " " }];
  const { unmount } = render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByRole("button", { name: "Create fast extractive draft" })).toHaveProperty("disabled", true);
  unmount();
  activeTranscript = [{ id: 1, start: 0, end: 1, text: "Xin chào" }];
  let release!: () => void;
  generationGate = new Promise<void>((resolve) => { release = resolve; });
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  const fast = await screen.findByRole("button", { name: "Create fast extractive draft" });
  await user.click(fast);
  expect(fast).toHaveProperty("disabled", true);
  release();
  await screen.findByText("Extracted locally from the transcript; not a semantic AI summary.");
});

it("preserves unsaved edits when the fast draft confirmation is declined", async () => {
  localAIReady = true; versionId = "m".repeat(32);
  const user = userEvent.setup();
  vi.stubGlobal("confirm", vi.fn(() => false));
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.type(screen.getByRole("textbox", { name: "Edit minutes Markdown" }), " Unsaved");
  await user.click(await screen.findByRole("button", { name: "Create fast extractive draft" }));
  expect((screen.getByRole("textbox", { name: "Edit minutes Markdown" }) as HTMLTextAreaElement).value).toContain("Unsaved");
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateOffline")).toBe(false);
});

it("reports extractive failures accurately even when local AI is installed", async () => {
  localAIReady = true; generationError = true;
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Create fast extractive draft" }));
  expect(await screen.findByText("Could not create meeting minutes. Check the saved transcript and try again.")).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateLocalStart")).toBe(false);
});

it("shows the one-click minutes controls in Vietnamese without review status", async () => {
  versionId = "m".repeat(32);
  localAIReady = true;
  useUIStore.setState({ language: "vi" });
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByRole("heading", { name: "Tạo biên bản" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Tạo biên bản" })).toBeTruthy();
  expect(await screen.findByRole("button", { name: "Tạo biên bản trích xuất nhanh" })).toBeTruthy();
  await waitFor(() => expect(screen.getByRole("article").textContent).toContain("Bản nháp"));
  expect(screen.queryByText("Chưa xác minh")).toBeNull();
});

it("explains missing and blank transcripts without generating", async () => {
  activeTranscript = null;
  const { unmount } = render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByRole("button", { name: "Generate meeting minutes" })).toHaveProperty("disabled", true);
  expect(screen.getByText("Transcribe this recording and save nonempty text before creating minutes.")).toBeTruthy();
  unmount();
  activeTranscript = [{ id: 1, start: 0, end: 1, text: "   " }];
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Generate meeting minutes" }).hasAttribute("disabled")).toBe(true));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateOffline")).toBe(false);
});

it("shows progress, blocks duplicate requests, and allows retry after failure", async () => {
  const user = userEvent.setup();
  let release!: () => void;
  generationGate = new Promise<void>((resolve) => { release = resolve; });
  generationError = true;
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  const action = await screen.findByRole("button", { name: "Generate meeting minutes" });
  await user.click(action);
  expect(screen.getByRole("button", { name: "Creating minutes…" }).hasAttribute("disabled")).toBe(true);
  expect(vi.mocked(bridgeCall).mock.calls.filter(([operation]) => operation === "minutes.generateOffline")).toHaveLength(1);
  release();
  const error = await screen.findByText("Could not create meeting minutes. Check the saved transcript and try again.");
  expect(error.closest(".minutes-create")).toBeTruthy();
  generationError = false;
  generationGate = null;
  await user.click(screen.getByRole("button", { name: "Generate meeting minutes" }));
  await waitFor(() => expect(screen.getByRole("article").textContent).toContain("Bản nháp"));
  expect(vi.mocked(bridgeCall).mock.calls.filter(([operation]) => operation === "minutes.generateOffline")).toHaveLength(2);
});

it("shows saved minutes even when source comparison is unavailable", async () => {
  domainMode = true; versionId = "m".repeat(32); sourceDriftError = true;
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  expect(await screen.findByRole("article")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
});

it("reports an outdated sidecar beside the action instead of appearing idle", async () => {
  versionId = "m".repeat(32); versionReadError = true;
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  const warning = await screen.findByRole("alert");
  expect(warning.textContent).toContain("desktop backend is out of date");
  expect(warning.closest(".minutes-create")).toBeTruthy();
});

it("reports a saved but unreadable draft after generation without creating another version", async () => {
  versionReadError = true;
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Generate meeting minutes" }));
  const warning = await screen.findByRole("alert");
  expect(warning.textContent).toContain("desktop backend is out of date");
  expect(warning.closest(".minutes-create")).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.filter(([operation]) => operation === "minutes.generateOffline")).toHaveLength(1);
});

it("keeps unsaved domain edits when regeneration is cancelled", async () => {
  domainMode = true; versionId = "m".repeat(32);
  const user = userEvent.setup();
  vi.stubGlobal("confirm", vi.fn(() => false));
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByText("Edit meeting details and notes"));
  await screen.findByRole("button", { name: "Topics" });
  await user.type(screen.getByRole("textbox", { name: "Objective" }), "Review rollout");
  await waitFor(() => expect(screen.getAllByText("Unsaved edits").length).toBeGreaterThan(0));
  await user.click(screen.getByRole("button", { name: "Generate meeting minutes" }));
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.generateOffline")).toBe(false);
  expect((screen.getByRole("textbox", { name: "Objective" }) as HTMLInputElement).value).toBe("Review rollout");
});

it("omits the redundant source list while keeping claim-level playback links", async () => {
  domainMode = true; versionId = "m".repeat(32);
  const user = userEvent.setup();
  const onSeek = vi.fn();
  const onOpenSource = vi.fn();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={onSeek} onOpenSource={onOpenSource} runVersion={0} />);
  await user.click(await screen.findByText("Edit meeting details and notes"));
  await user.click(await screen.findByRole("button", { name: "Topics" }));
  expect(screen.queryByText("Source timestamps")).toBeNull();
  await user.click(screen.getByRole("button", { name: /Seek source segment 1/ }));
  expect(onSeek).not.toHaveBeenCalled();
  expect(onOpenSource).toHaveBeenCalledWith("r".repeat(32), 0);
});

it("uses the selected type for the next draft until the user applies it to a saved version", async () => {
  domainMode = true; versionId = "m".repeat(32);
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByText("Edit meeting details and notes"));
  await screen.findByRole("button", { name: "Topics" });
  await user.selectOptions(screen.getByLabelText("Meeting type"), "requirement_gathering");
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.setType")).toBe(false);
  expect(screen.getByText("This type is used for specialized drafts.")).toBeTruthy();
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
  expect(screen.getByText("Unsaved edits")).toBeTruthy();
  expect(vi.mocked(exportSaved)).not.toHaveBeenCalled();
});

it("exports the selected saved minutes as Word after confirming unsaved edits", async () => {
  versionId = "m".repeat(32);
  const user = userEvent.setup();
  vi.stubGlobal("confirm", vi.fn(() => false));
  vi.mocked(exportSaved).mockResolvedValue({ saved: true, displayName: "minutes.docx" });
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.type(screen.getByRole("textbox", { name: "Edit minutes Markdown" }), " Unsaved");
  await user.click(screen.getByRole("button", { name: "Export Word (.docx)" }));
  expect(vi.mocked(exportSaved)).not.toHaveBeenCalled();
  vi.stubGlobal("confirm", vi.fn(() => true));
  await user.click(screen.getByRole("button", { name: "Export Word (.docx)" }));
  await waitFor(() => expect(vi.mocked(exportSaved)).toHaveBeenCalledWith(
    "a".repeat(32), versionId, "minutesWord"));
  expect(await screen.findByText("Exported minutes.docx.")).toBeTruthy();
});

it("keeps a dirty domain draft when version switching is cancelled", async () => {
  domainMode = true; versionId = "m".repeat(32); extraVersionId = "n".repeat(32);
  const user = userEvent.setup();
  vi.stubGlobal("confirm", vi.fn(() => false));
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted" onPrivacyChange={() => {}}
    onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByText("Edit meeting details and notes"));
  await user.click(await screen.findByRole("button", { name: "Topics" }));
  await user.type(screen.getByRole("textbox", { name: "Objective" }), "Review rollout");
  await waitFor(() => expect(screen.getAllByText("Unsaved edits").length).toBeGreaterThan(0));
  await user.selectOptions(screen.getByLabelText("Saved version"), extraVersionId);
  expect(vi.mocked(bridgeCall).mock.calls.some(([operation]) => operation === "minutes.select")).toBe(false);
  expect((screen.getByLabelText("Saved version") as HTMLSelectElement).value).toBe(versionId);
});


it("previews the draft, keeps it through transcript refresh, then saves and exports the new version", async () => {
  versionId = "m".repeat(32);
  const user = userEvent.setup();
  let savedBody = "";
  const fallback = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "minutes.edit") {
      savedBody = (params?.content as { user_text: string }).user_text;
      versionId = "n".repeat(32);
      return { versionId };
    }
    if (operation === "minutes.renderBody" && savedBody) return { markdown: savedBody };
    return fallback(operation, params);
  });
  vi.mocked(exportSaved).mockResolvedValue({ saved: true, displayName: "minutes.md" });
  const panel = (runVersion: number) => <MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={runVersion} />;
  const { rerender } = render(panel(0));
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.clear(screen.getByRole("textbox", { name: "Edit minutes Markdown" }));
  await user.type(screen.getByRole("textbox", { name: "Edit minutes Markdown" }), "A reviewed draft");
  await user.click(screen.getByRole("button", { name: "Preview" }));
  expect(screen.getByRole("article").textContent).toContain("A reviewed draft");
  expect(screen.getByRole("button", { name: "Save new version" })).toHaveProperty("disabled", false);
  rerender(panel(1));
  await user.click(screen.getByRole("button", { name: "Save new version" }));
  await waitFor(() => expect(savedBody).toBe("A reviewed draft"));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save new version" })).toHaveProperty("disabled", true));
  await user.click(screen.getByRole("button", { name: "Export MD" }));
  expect(vi.mocked(exportSaved)).toHaveBeenCalledWith("a".repeat(32), "n".repeat(32), "minutes");
});

it("retains both drafts when either conflicting save is declined", async () => {
  domainMode = true; versionId = "m".repeat(32);
  vi.stubGlobal("confirm", vi.fn(() => false));
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByText("Edit meeting details and notes"));
  await user.type(screen.getByRole("textbox", { name: "Participants (comma separated)" }), "An Nguyen, Bao Tran");
  expect(screen.getByRole("textbox", { name: "Participants (comma separated)" })).toHaveProperty("value", "An Nguyen, Bao Tran");
  await user.click(screen.getByRole("button", { name: "Edit" }));
  await user.type(screen.getByRole("textbox", { name: "Edit minutes Markdown" }), " changed");
  await user.click(screen.getByRole("button", { name: "Save new version" }));
  await user.click(screen.getByRole("button", { name: "Save notes as new version" }));
  expect(vi.mocked(bridgeCall).mock.calls.some(([op]) => op === "minutes.edit" || op === "minutes.editDomain")).toBe(false);
  expect(screen.getByRole("textbox", { name: "Participants (comma separated)" })).toHaveProperty("value", "An Nguyen, Bao Tran");
  expect((screen.getByRole("textbox", { name: "Edit minutes Markdown" }) as HTMLTextAreaElement).value).toContain("changed");
});

it("keeps the unsaved draft when selecting another version fails", async () => {
  versionId = "m".repeat(32); extraVersionId = "n".repeat(32);
  vi.stubGlobal("confirm", vi.fn(() => true));
  const fallback = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "minutes.select") throw new Error("select failed");
    return fallback(operation, params);
  });
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.type(screen.getByRole("textbox", { name: "Edit minutes Markdown" }), " retained");
  await user.selectOptions(screen.getByLabelText("Saved version"), extraVersionId);
  expect(await screen.findByText("Could not select this minutes version.")).toBeTruthy();
  expect((screen.getByRole("textbox", { name: "Edit minutes Markdown" }) as HTMLTextAreaElement).value).toContain("retained");
});


it("reports a successful edit even if refreshing the version list fails", async () => {
  versionId = "m".repeat(32);
  let didSave = false;
  const fallback = vi.mocked(bridgeCall).getMockImplementation()!;
  vi.mocked(bridgeCall).mockImplementation(async (operation, params) => {
    if (operation === "minutes.list" && didSave) throw new Error("list unavailable");
    if (operation === "minutes.edit") { didSave = true; versionId = "n".repeat(32); return { versionId }; }
    return fallback(operation, params);
  });
  const user = userEvent.setup();
  render(<MinutesPanel meetingId={"a".repeat(32)} privacyMode="restricted"
    onPrivacyChange={() => {}} onSeek={() => {}} runVersion={0} />);
  await user.click(await screen.findByRole("button", { name: "Edit" }));
  await user.type(screen.getByRole("textbox", { name: "Edit minutes Markdown" }), " change");
  await user.click(screen.getByRole("button", { name: "Save new version" }));
  expect(await screen.findByText("Minutes saved, but the list could not refresh. Reopen this meeting to view them.")).toBeTruthy();
  expect(vi.mocked(bridgeCall).mock.calls.filter(([op]) => op === "minutes.edit")).toHaveLength(1);
});
