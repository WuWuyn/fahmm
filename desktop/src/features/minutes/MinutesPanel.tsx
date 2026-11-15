import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Download, Save, ShieldCheck, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { bridgeCall, exportSaved } from "@/shared/bridge/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime, useT } from "@/shared/i18n";
import { useUIStore } from "@/shared/uiStore";

type VersionSummary = { version_id: string; created_at: string; review_state: string; origin: string };
type Version = { manifest: VersionSummary & { run_id: string }; content: Record<string, unknown> };
type Segment = { id: number; start: number; end: number; text: string };
type Profile = { id: string; name: string; base_url: string; model_id: string; hasKey: boolean };
type CloudPreview = { previewId: string; preview: {
  destination_hostname: string; warning: string; transcript: string; prompt: string;
  token_limit: number; request_body: Record<string, unknown>;
} };
type OfflineTemplate = { headings: Record<string, string>; guidance: string; topic_limit: number };
const PROMPTS = {
  structured: "Viết biên bản cuộc họp bằng tiếng Việt. Chỉ dùng các đoạn đã chọn và nêu rõ thông tin chưa xác minh.",
  concise: "Tạo biên bản tiếng Việt ngắn gọn từ các đoạn đã chọn. Liệt kê quyết định, việc cần làm và thông tin chưa xác minh.",
};

export function MinutesPanel({ meetingId, privacyMode, onPrivacyChange, onSeek, onOpenSource, runVersion }: {
  meetingId: string; privacyMode: string; onPrivacyChange: (mode: string) => void;
  onSeek: (seconds: number) => void; onOpenSource?: (runId: string, seconds: number) => void; runVersion: number;
}) {
  const t = useT();
  const language = useUIStore((state) => state.language);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [version, setVersion] = useState<Version | null>(null);
  const [savedBody, setSavedBody] = useState("");
  const [editBody, setEditBody] = useState("");
  const [editing, setEditing] = useState(false);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [reviewedIds, setReviewedIds] = useState<number[]>([]);
  const [prompt, setPrompt] = useState(PROMPTS.structured);
  const [maxTokens, setMaxTokens] = useState(2000);
  const [template, setTemplate] = useState<OfflineTemplate | null>(null);
  const [preview, setPreview] = useState<CloudPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messageName, setMessageName] = useState("");
  const dirty = editing && editBody !== savedBody;

  const refresh = useCallback(async () => {
    const [listing, providerList, runs, templateData] = await Promise.all([
      bridgeCall<{ versions: VersionSummary[]; activeVersionId: string | null }>("minutes.list", { meetingId }),
      bridgeCall<{ profiles: Profile[] }>("provider.list"),
      bridgeCall<{ activeRunId: string | null }>("transcript.list", { meetingId }),
      bridgeCall<{ template: OfflineTemplate }>("minutes.template", { meetingId }),
    ]);
    setVersions(listing.versions);
    setSelectedVersion((current) => current && listing.versions.some((item) => item.version_id === current)
      ? current : listing.activeVersionId || listing.versions[0]?.version_id || "");
    setProfiles(providerList.profiles);
    setTemplate(templateData.template);
    setProfileId((current) => providerList.profiles.some((profile) => profile.id === current)
      ? current : providerList.profiles[0]?.id || "");
    if (runs.activeRunId) {
      const active = await bridgeCall<{ run: { working: Segment[] } }>("transcript.read",
        { meetingId, runId: runs.activeRunId });
      setSegments(active.run.working);
    } else setSegments([]);
  }, [meetingId]);

  useEffect(() => { setSelectedVersion(""); setVersion(null); setSavedBody(""); setEditBody("");
    setSelectedIds([]); setReviewedIds([]); setEditing(false); setMessage("");
    void refresh().catch(() => setMessage("Could not load minutes and provider profiles."));
  }, [refresh, runVersion]);
  useEffect(() => {
    if (!selectedVersion) { setVersion(null); setSavedBody(""); return; }
    let alive = true;
    void Promise.all([
      bridgeCall<{ version: Version }>("minutes.read", { meetingId, versionId: selectedVersion }),
      bridgeCall<{ markdown: string }>("minutes.renderBody", { meetingId, versionId: selectedVersion }),
    ]).then(([data, rendered]) => {
      if (alive) { setVersion(data.version); setSavedBody(rendered.markdown); setEditBody(rendered.markdown); setEditing(false); }
    }).catch(() => { if (alive) setMessage("Could not open the selected minutes version."); });
    return () => { alive = false; };
  }, [meetingId, selectedVersion]);
  async function generateOffline() {
    setBusy(true); setMessage("");
    try {
      const data = await bridgeCall<{ versionId: string }>("minutes.generateOffline", { meetingId, runId: null });
      await refresh(); setSelectedVersion(data.versionId);
      setMessage("Offline extractive draft saved. Review its citations before approval.");
    } catch { setMessage("Could not create offline minutes. Save a transcript first."); }
    finally { setBusy(false); }
  }

  async function saveTemplate() {
    if (!template) return;
    try { await bridgeCall("minutes.saveTemplate", { meetingId, template });
      setMessage("Offline template saved for future drafts."); }
    catch { setMessage("Could not save the offline template. Check all headings and topic limit."); }
  }

  async function changePrivacy() {
    const mode = privacyMode === "restricted" ? "cloud_permitted" : "restricted";
    if (mode === "cloud_permitted" && !window.confirm(t("Allow this meeting to be shared with a provider? Each send will still require a payload preview and confirmation."))) return;
    try {
      await bridgeCall("meeting.privacy", { meetingId, mode });
      onPrivacyChange(mode);
    } catch { setMessage("Could not change this meeting's privacy mode."); }
  }

  async function saveEdit() {
    if (!version || !dirty) return;
    setBusy(true); setMessage("");
    try {
      const data = await bridgeCall<{ versionId: string }>("minutes.edit", {
        meetingId, versionId: selectedVersion, content: { ...version.content, user_text: editBody },
      });
      await refresh(); setSelectedVersion(data.versionId);
      setMessage("New unverified minutes version saved.");
    } catch { setMessage("Could not save the minutes edit."); }
    finally { setBusy(false); }
  }

  async function approve() {
    if (!version || dirty) return;
    try {
      await bridgeCall("minutes.approve", { meetingId, versionId: selectedVersion });
      const next = await bridgeCall<{ version: Version }>("minutes.read", { meetingId, versionId: selectedVersion });
      setVersion(next.version); await refresh(); setMessage("This saved version is approved.");
    } catch { setMessage("Could not approve this version."); }
  }

  async function exportMarkdown(copy: boolean) {
    if (!selectedVersion) return;
    if (dirty) {
      if (!window.confirm(t("Discard unsaved minutes edits and use the saved version? Cancel to save a new version first."))) return;
      setEditBody(savedBody); setEditing(false);
    }
    try {
      if (copy) {
        const saved = await bridgeCall<{ markdown: string }>("export.minutesMarkdown", { meetingId, versionId: selectedVersion });
        await navigator.clipboard.writeText(saved.markdown);
        setMessage("Saved Markdown copied.");
      } else {
        const result = await exportSaved(meetingId, selectedVersion, "minutes");
        if (result.saved) { setMessageName(result.displayName ?? ""); setMessage("Exported {name}."); }
      }
    } catch { setMessage("Could not export the saved minutes."); }
  }

  async function createPreview() {
    setBusy(true); setMessage("");
    try {
      const data = await bridgeCall<CloudPreview>("cloud.preview", {
        meetingId, profileId, selectedIds, reviewedIds, prompt, maxTokens,
      });
      setPreview(data);
    } catch { setMessage("Preview unavailable. Select and review transcript segments, then check the provider profile."); }
    finally { setBusy(false); }
  }

  async function cancelPreview() {
    if (!preview) return;
    const id = preview.previewId;
    setPreview(null);
    try { await bridgeCall("cloud.cancel", { previewId: id }); } catch { /* expiry also cancels */ }
  }

  async function confirmSend() {
    if (!preview) return;
    const id = preview.previewId;
    setBusy(true); setMessage("");
    try {
      await bridgeCall("cloud.confirm", { previewId: id, accepted: true });
      setPreview(null);
      const data = await bridgeCall<{ versionId: string }>("cloud.send", { previewId: id });
      await refresh(); setSelectedVersion(data.versionId);
      setMessage("Provider draft saved as unverified minutes.");
    } catch { setPreview(null); setMessage("Provider request failed. Review a new preview before retrying."); }
    finally { setBusy(false); }
  }

  const sources = (() => {
    if (!version) return [] as { run_id: string; segment_id: number; start: number }[];
    const found: { run_id: string; segment_id: number; start: number }[] = [];
    const visit = (value: unknown) => {
      if (Array.isArray(value)) { value.forEach(visit); return; }
      if (value && typeof value === "object") {
        const record = value as Record<string, unknown>;
        if (Array.isArray(record.sources)) record.sources.forEach((item) => {
          if (item && typeof item === "object" && "run_id" in item && "segment_id" in item && "start" in item) {
            found.push(item as { run_id: string; segment_id: number; start: number });
          }
        });
        Object.entries(record).filter(([key]) => key !== "sources").forEach(([, item]) => visit(item));
      }
    };
    visit(version.content);
    return [...new Map(found.map((item) => [item.segment_id, item])).values()].sort((a, b) => a.start - b.start);
  })();

  return <section className="document-panel" aria-label={t("Minutes")}>
    <div className="document-toolbar"><div><h2>{t("Meeting minutes")}</h2><p>{t("Every draft starts unverified.")}</p></div>
      <Button size="sm" disabled={busy || segments.length === 0} onClick={() => void generateOffline()}><Sparkles size={15} /> {t("Offline draft")}</Button></div>
    <details className="template-settings"><summary>{t("Edit offline template")}</summary>
      {template && <div className="template-fields">
        {Object.entries(template.headings).map(([key, value]) => <Label key={key}>{t(key.replace(/_/g, " "))}
          <Input value={value} onChange={(event) => setTemplate((current) => current ?
            { ...current, headings: { ...current.headings, [key]: event.target.value } } : current)} /></Label>)}
        <Label>{t("Guidance")}<Textarea value={template.guidance} onChange={(event) => setTemplate((current) => current ?
          { ...current, guidance: event.target.value } : current)} /></Label>
        <Label>{t("Topic limit")}<Input type="number" min={1} max={10} value={template.topic_limit}
          onChange={(event) => setTemplate((current) => current ? { ...current, topic_limit: Number(event.target.value) } : current)} /></Label>
        <Button variant="secondary" size="sm" onClick={() => void saveTemplate()}>{t("Save template")}</Button>
      </div>}
    </details>
    <div className="privacy-row"><span className="subheading">{t("Privacy classification")}</span>
      <Badge variant="outline" className={`privacy-badge${privacyMode === "cloud_permitted" ? " cloud" : ""}`}>{t(privacyMode === "restricted" ? "Local Only" : "Cloud Allowed")}</Badge>
      <Button variant="link" size="xs" onClick={() => void changePrivacy()}>{t("Change")}</Button></div>
    <div className="document-toolbar secondary"><Label htmlFor="minutes-version">{t("Saved version")}</Label>
      <NativeSelect id="minutes-version" value={selectedVersion} onChange={(event) => {
        if (dirty && !window.confirm(t("Discard unsaved minutes edits?"))) return;
        const nextVersion = event.target.value;
        if (!nextVersion) return;
        const previousVersion = selectedVersion;
        setSelectedVersion(nextVersion);
        void bridgeCall("minutes.select", { meetingId, versionId: nextVersion })
          .catch(() => { setSelectedVersion(previousVersion); setMessage("Could not select this minutes version."); });
      }}><option value="" disabled={versions.length > 0}>{t("No minutes yet")}</option>
        {versions.map((item) => <option key={item.version_id} value={item.version_id}>{formatDateTime(item.created_at, language)} · {t(item.origin)} · {t(item.review_state)}</option>)}
      </NativeSelect></div>
    {version && <div className="review-row"><Badge variant="outline" className={`review-badge ${version.manifest.review_state}`}>{t(version.manifest.review_state)}</Badge>
      <span className="hint">{t(version.manifest.origin === "extractive" ? "Source-linked extractive draft; not a semantic AI summary" : version.manifest.origin === "provider" ? "Provider draft; verify claims" : "Edited version")}</span></div>}
    {version && Array.isArray(version.content.actions) && version.content.actions.length > 0 &&
      <p className="hint">{t("Action entries in these minutes are suggestions, not assigned or tracked tasks.")}</p>}
    {!version && <div className="empty-document">{t("Create a draft from a saved transcript.")}</div>}
    {version && (editing ? <Textarea className="minutes-editor" aria-label={t("Edit minutes Markdown")} value={editBody} onChange={(event) => setEditBody(event.target.value)} />
      : <article className="markdown-body"><ReactMarkdown>{savedBody}</ReactMarkdown></article>)}
    {sources.length > 0 && <div className="citation-list"><strong>{t("Source timestamps")}</strong>
      {sources.map((source) => <Button key={source.segment_id} variant="link" size="xs" className="timestamp-button" onClick={() => onSeek(source.start)}>
        {t("Segment {id}", { id: source.segment_id })} · {source.start.toFixed(1)}s</Button>)}</div>}
    {onOpenSource && sources.length > 0 && <div className="citation-list"><strong>{t("Open transcript source")}</strong>
      {sources.map((source) => <Button key={source.segment_id} variant="link" size="xs" className="timestamp-button"
        onClick={() => onOpenSource(source.run_id, source.start)}>{t("Segment {id}", { id: source.segment_id })}</Button>)}</div>}
    {version && <div className="document-footer">
      <Button variant="secondary" size="sm" onClick={() => setEditing((value) => !value)}>{t(editing ? "Preview" : "Edit")}</Button>
      <Button size="sm" disabled={!dirty || busy} onClick={() => void saveEdit()}><Save size={15} /> {t("Save new version")}</Button>
      <Button variant="secondary" size="sm" disabled={dirty || version.manifest.review_state === "approved"} onClick={() => void approve()}><Check size={15} /> {t("Approve")}</Button>
      <Button variant="secondary" size="sm" onClick={() => void exportMarkdown(true)}><Copy size={15} /> {t("Copy Markdown")}</Button>
      <Button variant="secondary" size="sm" onClick={() => void exportMarkdown(false)}><Download size={15} /> {t("Export MD")}</Button>
      {dirty && <span className="dirty-label">{t("Unsaved edits")}</span>}</div>}
    <div className="cloud-section"><div className="cloud-header"><ShieldCheck size={19} /><div><h2>{t("Optional provider draft")}</h2><p>{t("Only selected, reviewed transcript segments are sent after you confirm the exact payload.")}</p></div></div>
      <Label htmlFor="provider-select">{t("Provider profile")}</Label>
      <NativeSelect id="provider-select" value={profileId} onChange={(event) => setProfileId(event.target.value)}><option value="">{t("No provider configured")}</option>
        {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.model_id}</option>)}
      </NativeSelect>
      <Label htmlFor="prompt-preset">{t("Prompt template")}</Label><NativeSelect id="prompt-preset" onChange={(event) => setPrompt(PROMPTS[event.target.value as keyof typeof PROMPTS])}>
        <option value="structured">{t("Structured Vietnamese minutes")}</option><option value="concise">{t("Concise Vietnamese minutes")}</option>
      </NativeSelect>
      <Label htmlFor="minutes-prompt">{t("Prompt")}</Label><Textarea id="minutes-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
      <Label htmlFor="token-limit">{t("Token limit")}</Label><Input id="token-limit" type="number" min={100} max={8000}
        value={maxTokens} onChange={(event) => setMaxTokens(Number(event.target.value))} />
      <div className="segment-choice-list">{segments.map((segment) => <div className="segment-choice" key={segment.id}>
        <label><input type="checkbox" checked={selectedIds.includes(segment.id)} onChange={(event) => setSelectedIds((current) => event.target.checked ? [...current, segment.id] : current.filter((id) => id !== segment.id))} />
          <span>{segment.start.toFixed(1)}s · {segment.text}</span></label>
        <label><input type="checkbox" checked={reviewedIds.includes(segment.id)} onChange={(event) => setReviewedIds((current) => event.target.checked ? [...current, segment.id] : current.filter((id) => id !== segment.id))} /> {t("Reviewed")}</label>
      </div>)}</div>
      <Button variant="secondary" size="sm" disabled={busy || privacyMode !== "cloud_permitted" || !profileId || selectedIds.length === 0}
        onClick={() => void createPreview()}>{t("Preview provider payload")}</Button>
      {privacyMode !== "cloud_permitted" && <p className="hint">{t("This meeting is Local Only. Change its classification before preparing a provider preview.")}</p>}
    </div>
    {message && <p className="feedback" role="status">{t(message, { name: messageName })}</p>}
    <Dialog open={!!preview} onOpenChange={(open) => { if (!open) void cancelPreview(); }}>
      {preview && <DialogContent className="preview-dialog" aria-label={t("Provider payload preview")}>
        <DialogHeader><DialogTitle>{t("Review provider send")}</DialogTitle><DialogDescription>{t(preview.preview.warning)}</DialogDescription></DialogHeader>
        <dl><dt>{t("Destination")}</dt><dd>{preview.preview.destination_hostname}</dd><dt>{t("Token limit")}</dt><dd>{preview.preview.token_limit}</dd></dl>
        <h3>{t("Exact request body")}</h3><pre>{JSON.stringify(preview.preview.request_body, null, 2)}</pre>
        <h3>{t("Transcript leaving this device")}</h3><pre>{preview.preview.transcript}</pre>
        <DialogFooter><Button variant="secondary" disabled={busy} onClick={() => void cancelPreview()}>{t("Cancel")}</Button>
          <Button disabled={busy} onClick={() => void confirmSend()}>{t("Confirm and send")}</Button></DialogFooter>
      </DialogContent>}
    </Dialog>
  </section>;
}
