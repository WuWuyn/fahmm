import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/shared/i18n";

export type DomainSource = { run_id: string; segment_id: number; start: number; end: number; excerpt: string };
export type DomainClaim = { item_id: string; text: string; sources: DomainSource[]; origin: string;
  review_status: "needs_review" | "confirmed" | "rejected"; kind?: string; formality?: string;
  owner?: string; due_date?: string; confirmation_status?: string; acceptance_status?: string };
export type DomainField = { value: string | string[] | null; provenance: string; sources: DomainSource[] };
export type DomainContent = { domain_schema_version: 1; domain: {
  meeting_type: string; metadata: Record<string, DomainField>; sections: Record<string, DomainClaim[]>;
}; user_text?: string };
export type DriftEntry = { location: string; source: DomainSource; current_text: string | null; drifted: boolean };

export const MEETING_TYPES = ["general", "requirement_gathering", "technical_discussion", "project_status", "issue_incident", "uat_feedback"];
const SECTION_LABELS: Record<string, string> = {
  summary: "Summary", topics: "Topics", requirements: "Requirements", decisions: "Decisions",
  proposed_solutions: "Proposed solutions", open_questions: "Open questions", risks_blockers: "Risks and blockers",
  actions: "Action suggestions", next_steps: "Next steps", technical_considerations: "Technical considerations",
  status_updates: "Status updates", incident_findings: "Incident findings", uat_observations: "UAT observations",
};
const COMMON_SECTIONS = ["summary", "topics", "decisions", "proposed_solutions", "open_questions", "risks_blockers", "actions", "next_steps"];
const TYPE_SECTIONS: Record<string, string[]> = {
  general: [], requirement_gathering: ["requirements"], technical_discussion: ["technical_considerations"],
  project_status: ["status_updates"], issue_incident: ["incident_findings"], uat_feedback: ["uat_observations"],
};
const KINDS: Record<string, string[]> = {
  requirements: ["business", "functional", "non_functional", "business_rule", "constraint", "assumption", "change"],
  risks_blockers: ["risk", "blocker", "dependency"],
  technical_considerations: ["architecture", "technology", "api_integration", "database", "security", "performance", "dependency", "alternative"],
  status_updates: ["progress", "milestone", "issue", "blocker", "risk", "dependency", "next_step"],
  incident_findings: ["problem", "impact", "finding", "suspected_cause", "confirmed_cause", "workaround", "resolution_proposal", "follow_up"],
  uat_observations: ["scenario", "observed_result", "customer_feedback", "defect", "change_request", "pending_confirmation", "acceptance"],
};

export function DomainMinutesReview({ content, drift, busy, onSave, onDirtyChange, onSeek, onOpenSource }: {
  content: DomainContent; drift: DriftEntry[]; busy: boolean; onSave: (content: DomainContent) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void; onSeek: (seconds: number) => void;
  onOpenSource?: (runId: string, seconds: number) => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState<DomainContent>(() => structuredClone(content));
  const dirty = JSON.stringify(draft) !== JSON.stringify(content);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  const update = (mutate: (next: DomainContent) => void) => {
    setDraft((current) => { const next = structuredClone(current); mutate(next); return next; });
  };
  const updateClaim = (section: string, index: number, patch: Partial<DomainClaim>) => update((next) => {
    Object.assign(next.domain.sections[section][index], patch);
  });
  const sections = [...COMMON_SECTIONS, ...(TYPE_SECTIONS[draft.domain.meeting_type] || [])];
  const metadata = draft.domain.metadata;
  return <div className="domain-review">
    <p className="hint">{t("Review each claim against its saved source. Internal approval is not customer sign-off.")}</p>
    {content.user_text !== undefined && <p className="hint">{t("This version displays freeform Markdown; claim edits will not change that body.")}</p>}
    <div className="domain-metadata">
      {(["title", "meeting_datetime", "project_customer", "participants", "objective"] as const).map((key) => {
        const field = metadata[key];
        const current = Array.isArray(field.value) ? field.value.join(", ") : field.value || "";
        return <div key={key}><Label htmlFor={`domain-${key}`}>{t(({ title: "Title", meeting_datetime: "Actual meeting date and time (ISO with timezone)",
          project_customer: "Project / customer", participants: "Participants (comma separated)", objective: "Objective" })[key])}</Label>
          <Input id={`domain-${key}`} value={current} onChange={(event) => update((next) => {
            const text = event.target.value.trim();
            const target = next.domain.metadata[key];
            target.value = key === "participants" ? text.split(",").map((part) => part.trim()).filter(Boolean)
              : key === "title" ? text || "Chưa rõ" : text || null;
            target.provenance = text ? "user_provided" : "unknown";
            target.sources = [];
          })} />
          <small>{t("Provenance")}: {t(field.provenance)}</small>
        </div>;
      })}
    </div>
    {sections.map((section) => <div className="domain-section" key={section}>
      <div className="document-toolbar secondary"><h3>{t(SECTION_LABELS[section])}</h3>
        <Button variant="secondary" size="xs" onClick={() => update((next) => {
          const claim: DomainClaim = { item_id: crypto.randomUUID().replace(/-/g, ""), text: "",
            sources: [], origin: "user_provided", review_status: "needs_review" };
          if (KINDS[section]) claim.kind = KINDS[section][0];
          if (section === "requirements") claim.formality = "candidate";
          if (section === "actions") Object.assign(claim, { owner: "Chưa rõ", due_date: "Chưa rõ", confirmation_status: "suggested" });
          if (section === "uat_observations") claim.acceptance_status = "pending";
          (next.domain.sections[section] ||= []).push(claim);
        })}>{t("Add claim")}</Button></div>
      {(draft.domain.sections[section] || []).map((claim, index) => <div className="domain-claim" key={claim.item_id}>
        <Label htmlFor={`claim-${claim.item_id}`}>{t("Claim text")}<Textarea id={`claim-${claim.item_id}`} value={claim.text} onChange={(event) => updateClaim(section, index,
          { text: event.target.value, origin: "user_provided", review_status: "needs_review" })} /></Label>
        <div className="domain-claim-controls">
          <Label htmlFor={`review-${claim.item_id}`}>{t("Review state")}<NativeSelect id={`review-${claim.item_id}`} value={claim.review_status} onChange={(event) => updateClaim(section, index,
            { review_status: event.target.value as DomainClaim["review_status"] })}>
            {["needs_review", "confirmed", "rejected"].map((status) => <option key={status} value={status}>{t(status)}</option>)}
          </NativeSelect></Label>
          {claim.kind && <Label htmlFor={`kind-${claim.item_id}`}>{t("Classification")}<NativeSelect id={`kind-${claim.item_id}`} value={claim.kind} onChange={(event) => updateClaim(section, index,
            { kind: event.target.value, review_status: "needs_review" })}>
            {KINDS[section].map((kind) => <option key={kind} value={kind}>{t(kind)}</option>)}
          </NativeSelect></Label>}
          {section === "requirements" && <Label htmlFor={`formality-${claim.item_id}`}>{t("Formality")}<NativeSelect id={`formality-${claim.item_id}`} value={claim.formality} onChange={(event) => updateClaim(section, index,
            { formality: event.target.value, review_status: "needs_review" })}>
            {["candidate", "user_confirmed"].map((value) => <option key={value} value={value}>{t(value)}</option>)}
          </NativeSelect></Label>}
          {section === "uat_observations" && <Label htmlFor={`acceptance-${claim.item_id}`}>{t("Acceptance state")}<NativeSelect id={`acceptance-${claim.item_id}`} value={claim.acceptance_status} onChange={(event) => updateClaim(section, index,
            { acceptance_status: event.target.value, review_status: "needs_review" })}>
            {["pending", "user_confirmed"].map((value) => <option key={value} value={value}>{t(value)}</option>)}
          </NativeSelect></Label>}
        </div>
        {section === "actions" && <div className="domain-claim-controls">
          {(["owner", "due_date"] as const).map((field) => <Label key={field} htmlFor={`${field}-${claim.item_id}`}>{t(field === "owner" ? "Suggested owner" : "Suggested deadline")}
            <Input id={`${field}-${claim.item_id}`} value={claim[field] || ""} onChange={(event) => updateClaim(section, index,
              { [field]: event.target.value || "Chưa rõ", review_status: "needs_review" })} /></Label>)}
        </div>}
        <small>{t("Origin")}: {t(claim.origin)} · {claim.item_id.slice(0, 8)}</small>
        {claim.sources.map((source) => {
          const current = drift.find((entry) => entry.location === `sections.${section}.${claim.item_id}` && entry.source.segment_id === source.segment_id);
          const stale = current?.drifted && current.source.excerpt === source.excerpt;
          return <div className="domain-source" key={`${source.run_id}-${source.segment_id}`}>
            <Button variant="link" size="xs" onClick={() => { onSeek(source.start); onOpenSource?.(source.run_id, source.start); }}>
              {t("Seek source segment {id}", { id: source.segment_id })} · {source.start.toFixed(1)}s</Button>
            <p>{t("Saved excerpt")}: {source.excerpt}</p>
            {stale && <p role="alert">{t("Transcript changed since this draft")}: {current.current_text ?? t("Source segment missing")}</p>}
            {stale && current.current_text && <Button variant="secondary" size="xs" onClick={() => update((next) => {
              next.domain.sections[section][index].sources.find((item) => item.segment_id === source.segment_id)!.excerpt = current.current_text!;
              next.domain.sections[section][index].review_status = "needs_review";
            })}>{t("Use current transcript excerpt and review again")}</Button>}
            {stale && <Button variant="secondary" size="xs" onClick={() => update((next) => {
              const target = next.domain.sections[section][index];
              target.sources = target.sources.filter((item) => item.segment_id !== source.segment_id);
              target.origin = "user_provided";
              target.review_status = "needs_review";
            })}>{t("Remove outdated citation")}</Button>}
          </div>;
        })}
        {claim.sources.length === 0 && <p className="hint">{t("User-provided; no transcript citation")}</p>}
      </div>)}
    </div>)}
    <Button size="sm" disabled={!dirty || busy} onClick={() => void onSave(draft)}>{t("Save reviewed claims as new version")}</Button>
    {dirty && <span className="dirty-label">{t("Unsaved edits")}</span>}
  </div>;
}
