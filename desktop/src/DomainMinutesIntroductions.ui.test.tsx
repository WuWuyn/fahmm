// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DomainMinutesReview } from "@/features/minutes/DomainMinutesReview";
import type { DomainContent } from "@/features/minutes/DomainMinutesReview";
import { useUIStore } from "@/shared/uiStore";

const source = { run_id: "b".repeat(32), segment_id: 1, start: 0, end: 2, excerpt: "Review API" };
function content(): DomainContent {
  return { domain_schema_version: 1, domain: {
    meeting_type: "general", metadata: {
      title: { value: "Client call", provenance: "user_provided", sources: [] },
      meeting_datetime: { value: null, provenance: "unknown", sources: [] },
      project_customer: { value: null, provenance: "unknown", sources: [] },
      participants: { value: [], provenance: "unknown", sources: [] },
      objective: { value: null, provenance: "unknown", sources: [] },
    }, sections: { actions: [{ item_id: "a".repeat(32), text: "Review API", sources: [source],
      origin: "extractive", review_status: "needs_review", owner: "Chưa rõ", due_date: "Chưa rõ", confirmation_status: "suggested" }] },
  } };
}

afterEach(() => { cleanup(); useUIStore.setState({ language: "en" }); vi.clearAllMocks(); });

it("saves an introduction and action edits together, preserving sources when reopened", async () => {
  const user = userEvent.setup();
  const onSave = vi.fn(async (_next: DomainContent) => {});
  const onDirtyChange = vi.fn();
  const props = { drift: [], busy: false, onSave, onDirtyChange, onSeek: vi.fn() };
  const view = render(<DomainMinutesReview content={content()} {...props} />);
  await user.click(screen.getByRole("button", { name: "Action suggestions" }));
  await user.type(screen.getByRole("textbox", { name: "Introduction for Action suggestions" }), "Please review these tasks.");
  await user.clear(screen.getByRole("textbox", { name: "Suggested owner" }));
  await user.type(screen.getByRole("textbox", { name: "Suggested owner" }), "An");
  await user.clear(screen.getByRole("textbox", { name: "Suggested deadline" }));
  await user.type(screen.getByRole("textbox", { name: "Suggested deadline" }), "Friday");
  expect(screen.getByText("Unsaved edits")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Save notes as new version" }));
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
  const saved = onSave.mock.calls[0][0];
  expect(saved.domain.section_introductions).toEqual({ actions: "Please review these tasks." });
  expect(saved.domain.sections.actions[0]).toMatchObject({ text: "Review API", owner: "An", due_date: "Friday", sources: [source] });
  view.unmount();
  render(<DomainMinutesReview content={saved} {...props} />);
  await user.click(screen.getByRole("button", { name: "Action suggestions" }));
  expect(screen.getByRole("textbox", { name: "Introduction for Action suggestions" })).toHaveProperty("value", "Please review these tasks.");
  expect(screen.getByRole("textbox", { name: "Suggested owner" })).toHaveProperty("value", "An");
});

it("removes a blank introduction on save and keeps the other sections", async () => {
  const user = userEvent.setup();
  const previous = content();
  previous.domain.section_introductions = { actions: "Old introduction", topics: "Discussion follows." };
  const onSave = vi.fn(async (_next: DomainContent) => {});
  render(<DomainMinutesReview content={previous} drift={[]} busy={false} onSave={onSave}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Action suggestions" }));
  const introduction = screen.getByRole("textbox", { name: "Introduction for Action suggestions" });
  await user.clear(introduction);
  await user.type(introduction, "   ");
  await user.click(screen.getByRole("button", { name: "Save notes as new version" }));
  expect(onSave.mock.calls[0][0].domain.section_introductions).toEqual({ topics: "Discussion follows." });
});

it("allows an introduction in a DENSO project-actions section", async () => {
  const user = userEvent.setup();
  const denso = { ...content(), format: "denso_warehouse" };
  const onSave = vi.fn(async (_next: DomainContent) => {});
  render(<DomainMinutesReview content={denso} drift={[]} busy={false} onSave={onSave}
    onDirtyChange={vi.fn()} onSeek={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Project team actions" }));
  await user.type(screen.getByRole("textbox", { name: "Introduction for Project team actions" }), "Work proposed by the project team.");
  await user.click(screen.getByRole("button", { name: "Next steps" }));
  await user.type(screen.getByRole("textbox", { name: "Introduction for Next steps" }), "Continue with the following steps.");
  await user.click(screen.getByRole("button", { name: "Save notes as new version" }));
  expect(onSave.mock.calls[0][0].domain.section_introductions).toEqual({
    project_actions: "Work proposed by the project team.", next_steps: "Continue with the following steps.",
  });
});
