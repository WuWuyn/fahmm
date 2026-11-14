import { useCallback, useEffect, useState } from "react";
import { Copy, Download, Save, WandSparkles, X } from "lucide-react";
import { bridgeCall, exportSaved } from "@/shared/bridge/client";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";

type Segment = { id: number; start: number; end: number; text: string };
type Run = { manifest: { run_id: string; created_at: string; model_repository: string }; original: Segment[]; working: Segment[] };
type RunSummary = { run_id: string; created_at: string; model_repository: string };
type AsrStatus = { state: string; meetingId: string | null; runId: string | null; progress: number | null; segmentCount: number; error: string | null };

function timestamp(seconds: number) {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

export function TranscriptPanel({ meetingId, onSeek, onRunChange }: {
  meetingId: string; onSeek: (seconds: number) => void; onRunChange: () => void;
}) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [working, setWorking] = useState<Segment[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [language, setLanguage] = useState("vi");
  const [status, setStatus] = useState<AsrStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const dirty = !!run && working.some((segment, index) => segment.text !== run.working[index]?.text);

  const refreshRuns = useCallback(async () => {
    const [listing, catalog] = await Promise.all([
      bridgeCall<{ runs: RunSummary[]; activeRunId: string | null }>("transcript.list", { meetingId }),
      bridgeCall<{ selectedId: string | null }>("model.catalog"),
    ]);
    setRuns(listing.runs);
    setSelectedModel(catalog.selectedId);
    setSelectedRun((current) => current && listing.runs.some((item) => item.run_id === current)
      ? current : listing.activeRunId || listing.runs[0]?.run_id || "");
  }, [meetingId]);

  useEffect(() => { setRun(null); setWorking([]); setSelectedRun(""); setMessage("");
    void refreshRuns().catch(() => setMessage("Could not load transcript runs."));
  }, [refreshRuns]);
  useEffect(() => {
    if (!selectedRun) { setRun(null); setWorking([]); return; }
    let alive = true;
    void bridgeCall<{ run: Run }>("transcript.read", { meetingId, runId: selectedRun })
      .then(({ run }) => { if (alive) { setRun(run); setWorking(run.working.map((segment) => ({ ...segment }))); } })
      .catch(() => { if (alive) setMessage("Could not open the selected transcript."); });
    return () => { alive = false; };
  }, [meetingId, selectedRun]);
  useEffect(() => {
    const read = () => { void bridgeCall<AsrStatus>("asr.status").then((next) => {
      setStatus((prior) => {
        if (next.state === "completed" && prior?.state !== "completed" && next.meetingId === meetingId) {
          void refreshRuns().then(onRunChange);
        }
        return next;
      });
    }).catch(() => undefined); };
    read();
    const timer = window.setInterval(read, 900);
    return () => window.clearInterval(timer);
  }, [meetingId, onRunChange, refreshRuns]);

  async function save() {
    if (!run || !dirty) return;
    setBusy(true); setMessage("");
    try {
      const edits: Record<string, string> = {};
      working.forEach((segment, index) => {
        if (segment.text !== run.working[index]?.text) edits[String(segment.id)] = segment.text;
      });
      await bridgeCall("transcript.saveEdits", { meetingId, runId: selectedRun, edits });
      const updated = await bridgeCall<{ run: Run }>("transcript.read", { meetingId, runId: selectedRun });
      setRun(updated.run); setWorking(updated.run.working.map((segment) => ({ ...segment })));
      setMessage("Transcript edits saved locally."); onRunChange();
    } catch { setMessage("Could not save transcript edits."); }
    finally { setBusy(false); }
  }

  async function startOrRetry(retry: boolean) {
    if (!selectedModel && !retry) { setMessage("Install a local model in Models first."); return; }
    setBusy(true); setMessage("");
    try {
      await bridgeCall(retry ? "asr.retry" : "asr.start", retry ? {} :
        { meetingId, modelId: selectedModel, language });
    } catch { setMessage("Could not start transcription. Check the local model and audio."); }
    finally { setBusy(false); }
  }

  async function exportText(copy: boolean) {
    if (!selectedRun) return;
    if (dirty) {
      if (!window.confirm("Discard unsaved transcript edits and use the saved version? Cancel to save edits first.")) return;
      if (run) setWorking(run.working.map((segment) => ({ ...segment })));
    }
    setMessage("");
    try {
      if (copy) {
        const saved = await bridgeCall<{ text: string }>("export.transcriptText", { meetingId, runId: selectedRun });
        await navigator.clipboard.writeText(saved.text);
        setMessage("Saved transcript copied.");
      } else {
        const result = await exportSaved(meetingId, selectedRun, "transcript");
        if (result.saved) setMessage(`Exported ${result.displayName}.`);
      }
    } catch { setMessage("Could not export the saved transcript."); }
  }

  const activeJob = status?.meetingId === meetingId && ["loading", "running", "cancelling"].includes(status.state);
  return <section className="document-panel" aria-label="Transcript">
    <div className="document-toolbar"><div><h2>Transcript</h2><p>Review and correct timestamped speech.</p></div>
      <div className="toolbar-actions">
        <Label htmlFor="speech-language">Speech language</Label>
        <NativeSelect id="speech-language" value={language} disabled={activeJob} onChange={(event) => setLanguage(event.target.value)}>
          <option value="vi">Vietnamese (default)</option><option value="auto">Auto detect</option><option value="en">English</option>
        </NativeSelect>
        <Button size="sm" disabled={busy || activeJob || !selectedModel} onClick={() => void startOrRetry(false)}><WandSparkles size={15} /> Transcribe</Button>
        {activeJob && <Button variant="secondary" size="sm" onClick={() => void bridgeCall("asr.cancel").catch(() => setMessage("Could not cancel transcription."))}><X size={15} /> Cancel</Button>}
        {status?.state === "error" && status.meetingId === meetingId && <Button variant="secondary" size="sm" onClick={() => void startOrRetry(true)}>Retry</Button>}
      </div></div>
    {activeJob && <div className="job-progress"><span>{status?.state === "loading" ? "Loading model" : status?.state === "cancelling" ? "Cancelling" : "Transcribing"}</span>
      <Progress value={status?.progress == null ? null : Math.round(status.progress * 100)} aria-label="Transcription progress" /> <span>{status?.progress == null ? "" : `${Math.round(status.progress * 100)}%`}</span></div>}
    {status?.state === "error" && status.meetingId === meetingId && <div className="alert" role="alert">{status.error || "Transcription failed."}</div>}
    <div className="document-toolbar secondary"><Label htmlFor="run-select">Saved run</Label>
      <NativeSelect id="run-select" value={selectedRun} onChange={(event) => {
        if (dirty && !window.confirm("Discard unsaved transcript edits?")) return;
        const nextRun = event.target.value;
        if (!nextRun) return;
        const previousRun = selectedRun;
        setSelectedRun(nextRun);
        void bridgeCall("transcript.select", { meetingId, runId: nextRun }).then(onRunChange)
          .catch(() => { setSelectedRun(previousRun); setMessage("Could not select this transcript run."); });
      }}><option value="" disabled={runs.length > 0}>No transcript yet</option>
        {runs.map((item) => <option key={item.run_id} value={item.run_id}>{new Date(item.created_at).toLocaleString()} · {item.model_repository}</option>)}
      </NativeSelect></div>
    {!selectedModel && <p className="hint">A local speech model is required. Install one in Models; no cloud fallback is used.</p>}
    {working.length === 0 && <div className="empty-document">No saved transcript for this meeting.</div>}
    <div className="segment-list">{working.map((segment, index) => <div className="segment" key={segment.id}>
      <Button variant="link" size="xs" className="timestamp-button" onClick={() => onSeek(segment.start)} title="Seek audio to this segment">{timestamp(segment.start)}</Button>
      <div><Textarea aria-label={`Transcript segment ${segment.id}`} value={segment.text}
        onChange={(event) => setWorking((current) => current.map((item, i) => i === index ? { ...item, text: event.target.value } : item))} />
        {run && segment.text !== run.original[index]?.text && <small>Original ASR: {run.original[index]?.text}</small>}
      </div></div>)}</div>
    <div className="document-footer"><Button size="sm" disabled={!dirty || busy} onClick={() => void save()}><Save size={15} /> Save edits</Button>
      <Button variant="secondary" size="sm" disabled={!selectedRun} onClick={() => void exportText(true)}><Copy size={15} /> Copy saved</Button>
      <Button variant="secondary" size="sm" disabled={!selectedRun} onClick={() => void exportText(false)}><Download size={15} /> Export TXT</Button>
      {dirty && <span className="dirty-label">Unsaved edits</span>}</div>
    {message && <p className="feedback" role="status">{message}</p>}
  </section>;
}
