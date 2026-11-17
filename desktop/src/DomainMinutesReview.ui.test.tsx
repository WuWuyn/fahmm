// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
  expect(screen.getByText("Summary")).toBeTruthy();
  expect(screen.getByText("Topics")).toBeTruthy();
  expect(screen.getByDisplayValue("Review API")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Save reviewed claims as new version" }).hasAttribute("disabled")).toBe(true);
  const special: Record<string, string | null> = { general: null, requirement_gathering: "Requirements",
    technical_discussion: "Technical considerations", project_status: "Status updates",
    issue_incident: "Incident findings", uat_feedback: "UAT observations" };
  if (special[kind]) expect(screen.getByText(special[kind]!)).toBeTruthy();
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

it("switches controls to Vietnamese without changing saved content", () => {
  const draft = content("technical_discussion");
  const view = render(<DomainMinutesReview content={draft} drift={[]} busy={false} onSave={vi.fn()}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  expect(screen.getByText("Technical considerations")).toBeTruthy();
  useUIStore.getState().setLanguage("vi");
  view.rerender(<DomainMinutesReview content={draft} drift={[]} busy={false} onSave={vi.fn()}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  expect(screen.getByText("Nội dung kỹ thuật")).toBeTruthy();
  expect(draft.domain.sections.topics[0].text).toBe("Review API");
});
