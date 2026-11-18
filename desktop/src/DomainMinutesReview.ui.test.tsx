// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DomainMinutesReview, type DomainContent, type DriftEntry, MEETING_TYPES } from "@/features/minutes/DomainMinutesReview";
import { useUIStore } from "@/shared/uiStore";

function content(meetingType: string): DomainContent {
  const field = (value: string | string[] | null, provenance = "unknown") => ({ value, provenance, sources: [] });
  return { domain_schema_version: 1, domain: {
    meeting_type: meetingType,
    metadata: { title: field("Client call", "user_provided"), meeting_datetime: field(null),
      project_customer: field(null), participants: field([]), objective: field(null) },
    sections: { topics: [{ item_id: "a".repeat(32), text: "Review API", origin: "extractive",
      review_status: "needs_review", sources: [{ run_id: "r".repeat(32), segment_id: 1,
        start: 0, end: 2, excerpt: "Review API" }] }] },
  } };
}

afterEach(() => { cleanup(); useUIStore.getState().setLanguage("en"); });

it.each(MEETING_TYPES)("renders domain review controls for %s", (kind) => {
  render(<DomainMinutesReview content={content(kind)} drift={[]} busy={false} onSave={vi.fn()}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Summary" }).getAttribute("aria-expanded")).toBe("false");
  expect(screen.getByRole("button", { name: "Topics" }).getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByDisplayValue("Review API")).toBeNull();
  expect(screen.getByRole("button", { name: "Save reviewed claims as new version" }).hasAttribute("disabled")).toBe(true);
  const special: Record<string, string | null> = { general: null, requirement_gathering: "Requirements",
    technical_discussion: "Technical considerations", project_status: "Status updates",
    issue_incident: "Incident findings", uat_feedback: "UAT observations" };
  if (special[kind]) expect(screen.getByText(special[kind]!)).toBeTruthy();
  if (kind === "general") {
    for (const heading of ["Requirements", "Decisions", "Proposed solutions", "Action suggestions",
      "Open questions", "Risks and blockers", "Next steps", "Technical considerations"]) {
      expect(screen.getByText(heading)).toBeTruthy();
    }
  }
});

it("shows saved excerpt, warns about drift, seeks audio, and saves a reviewed correction", async () => {
  const user = userEvent.setup();
  const onSave = vi.fn(async (_draft: DomainContent) => undefined);
  const onSeek = vi.fn();
  const drift: DriftEntry[] = [{ location: `sections.topics.${"a".repeat(32)}`,
    source: content("general").domain.sections.topics[0].sources[0],
    current_text: "Updated API", drifted: true }];
  render(<DomainMinutesReview content={content("general")} drift={drift} busy={false}
    onSave={onSave} onDirtyChange={vi.fn()} onSeek={onSeek} />);
  await user.click(screen.getByRole("button", { name: "Topics" }));
  expect(screen.getByText(/Saved excerpt: Review API/)).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain("Updated API");
  await user.click(screen.getByRole("button", { name: /Seek source segment 1/ }));
  expect(onSeek).toHaveBeenCalledWith(0);
  await user.click(screen.getByRole("button", { name: "Use current transcript excerpt and review again" }));
  const status = screen.getAllByRole("combobox")[0];
  await user.selectOptions(status, "confirmed");
  await user.click(screen.getByRole("button", { name: "Save reviewed claims as new version" }));
  await waitFor(() => expect(onSave).toHaveBeenCalled());
  const saved = onSave.mock.calls[0][0] as DomainContent;
  expect(saved.domain.sections.topics[0].sources[0].excerpt).toBe("Updated API");
  expect(saved.domain.sections.topics[0].review_status).toBe("confirmed");
});

it("can add and remove a blank claim without leaving the draft dirty", async () => {
  const user = userEvent.setup();
  render(<DomainMinutesReview content={content("general")} drift={[]} busy={false} onSave={vi.fn()}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  const decisions = screen.getByText("Decisions").closest(".domain-section") as HTMLElement;
  await user.click(within(decisions).getByRole("button", { name: "Add claim" }));
  expect(within(decisions).getByRole("button", { name: "Decisions" }).getAttribute("aria-expanded")).toBe("true");
  expect(within(decisions).getByRole("textbox", { name: "Claim text" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Save reviewed claims as new version" }).hasAttribute("disabled")).toBe(false);
  await user.click(within(decisions).getByRole("button", { name: /Remove claim/ }));
  expect(within(decisions).queryByRole("textbox", { name: "Claim text" })).toBeNull();
  expect(screen.getByRole("button", { name: "Save reviewed claims as new version" }).hasAttribute("disabled")).toBe(true);
});

it("removes a saved claim from the new version without changing the original", async () => {
  const user = userEvent.setup();
  const original = content("general");
  const onSave = vi.fn(async (_draft: DomainContent) => undefined);
  render(<DomainMinutesReview content={original} drift={[]} busy={false} onSave={onSave}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  const topics = screen.getByText("Topics").closest(".domain-section") as HTMLElement;
  await user.click(within(topics).getByRole("button", { name: "Topics" }));
  await user.click(within(topics).getByRole("button", { name: "Remove claim aaaaaaaa" }));
  expect(within(topics).queryByRole("textbox", { name: "Claim text" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Save reviewed claims as new version" }));
  await waitFor(() => expect(onSave).toHaveBeenCalled());
  expect((onSave.mock.calls[0][0] as DomainContent).domain.sections.topics).toBeUndefined();
  expect(original.domain.sections.topics[0].text).toBe("Review API");
});

it("confirms and saves every claim across collapsed sections in one action", async () => {
  const user = userEvent.setup();
  const original = content("general");
  original.domain.sections.decisions = [{ item_id: "b".repeat(32), text: "Use API", origin: "user_provided",
    review_status: "rejected", sources: [] }];
  original.domain.sections.actions = [{ item_id: "c".repeat(32), text: "Document API", origin: "user_provided",
    review_status: "confirmed", sources: [], owner: "Mai", due_date: "Chưa rõ", confirmation_status: "suggested" }];
  const onSave = vi.fn(async (_draft: DomainContent) => undefined);
  render(<DomainMinutesReview content={original} drift={[]} busy={false} onSave={onSave}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  expect(screen.getByText("1 of 3 claims confirmed")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Confirm all claims" }));
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
  const saved = onSave.mock.calls[0][0] as DomainContent;
  expect(Object.values(saved.domain.sections).flat().map((claim) => claim.review_status))
    .toEqual(["confirmed", "confirmed", "confirmed"]);
  expect(saved.domain.sections.topics[0].sources).toEqual(original.domain.sections.topics[0].sources);
  expect(saved.domain.sections.decisions[0].item_id).toBe(original.domain.sections.decisions[0].item_id);
  expect(original.domain.sections.topics[0].review_status).toBe("needs_review");
  expect(original.domain.sections.decisions[0].review_status).toBe("rejected");
});

it("disables bulk confirmation when all claims are already confirmed", () => {
  const draft = content("general");
  draft.domain.sections.topics[0].review_status = "confirmed";
  render(<DomainMinutesReview content={draft} drift={[]} busy={false} onSave={vi.fn()}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Confirm all claims" }).hasAttribute("disabled")).toBe(true);
});

it("switches controls to Vietnamese without changing saved content", async () => {
  const user = userEvent.setup();
  const draft = content("technical_discussion");
  const view = render(<DomainMinutesReview content={draft} drift={[]} busy={false} onSave={vi.fn()}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  expect(screen.getByText("Technical considerations")).toBeTruthy();
  useUIStore.getState().setLanguage("vi");
  view.rerender(<DomainMinutesReview content={draft} drift={[]} busy={false} onSave={vi.fn()}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  expect(screen.getByText("Nội dung kỹ thuật")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Chủ đề" }));
  expect(screen.getByRole("button", { name: "Xóa nhận định aaaaaaaa" })).toBeTruthy();
  expect(draft.domain.sections.topics[0].text).toBe("Review API");
});
