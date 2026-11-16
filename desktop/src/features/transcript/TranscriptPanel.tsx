import { useCallback, useEffect, useState } from "react";
import { CirclePlay, Copy, Download, Info, Save, Settings2, WandSparkles, X } from "lucide-react";
import { bridgeCall, exportSaved } from "@/shared/bridge/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime, useT } from "@/shared/i18n";
import { useUIStore } from "@/shared/uiStore";

type Segment = { id: number; start: number; end: number; text: string };
type Run = { manifest: { run_id: string; created_at: string; model_repository: string; start_seconds?: number }; original: Segment[]; working: Segment[] };
type RunSummary = { run_id: string; created_at: string; model_repository: string; start_seconds?: number };
type AsrStatus = { state: string; meetingId: string | null; runId: string | null; progress: number | null; segmentCount: number; error: string | null };

function timestamp(seconds: number) {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function startTimeLabel(seconds: number): string {
  const tenths = Math.round(seconds * 10);
  const whole = Math.floor(tenths / 10);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}.${tenths % 10}`;
}

function parseStartTime(value: string): number | null {
  if (!value.trim()) return 0;
  const parts = value.trim().split(":");
  if ((parts.length !== 2 && parts.length !== 3) || parts.slice(0, -1).some((part) => !/^\d+$/.test(part))) return null;
  if (!/^\d{2}(?:\.\d{1,3})?$/.test(parts[parts.length - 1])) return null;
  const numbers = parts.map(Number);
  if (numbers[numbers.length - 1] >= 60) return null;
  if (parts.length === 3 && (parts[1].length !== 2 || numbers[1] >= 60)) return null;
  const seconds = parts.length === 3 ? numbers[0] * 3600 + numbers[1] * 60 + numbers[2] : numbers[0] * 60 + numbers[1];
  return Number.isFinite(seconds) && seconds <= Number.MAX_SAFE_INTEGER ? seconds : null;
}

export function TranscriptPanel({ meetingId, onSeek, onRunChange, playheadSeconds = 0, audioDurationSeconds = 0 }: {
  meetingId: string; onSeek: (seconds: number) => void; onRunChange: () => void;
  playheadSeconds?: number; audioDurationSeconds?: number;
}) {
  const t = useT();
  const languageUI = useUIStore((state) => state.language);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [working, setWorking] = useState<Segment[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [language, setLanguage] = useState("vi");
  const [startTime, setStartTime] = useState("00:00");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [status, setStatus] = useState<AsrStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messageName, setMessageName] = useState("");
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

  useEffect(() => { setRun(null); setWorking([]); setSelectedRun(""); setStartTime("00:00"); setSettingsOpen(false); setMessage("");
    void refreshRuns().catch(() => setMessage("Could not load transcript runs."));
  }, [refreshRuns]);
  useEffect(() => { setSettingsOpen(false); }, [selectedRun]);
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
    const startSeconds = parseStartTime(startTime);
    if (!retry && (startSeconds === null || (audioDurationSeconds > 0 && startSeconds >= audioDurationSeconds))) {
      setMessage("Choose a start time before the end of this recording (MM:SS or HH:MM:SS)."); return;
    }
    setBusy(true); setMessage("");
    try {
      await bridgeCall(retry ? "asr.retry" : "asr.startFrom", retry ? {} :
        { meetingId, modelId: selectedModel, language, startSeconds });
    } catch { setMessage("Could not start transcription. Check the local model and audio."); }
    finally { setBusy(false); }
  }

  async function exportText(copy: boolean) {
    if (!selectedRun) return;
    if (dirty) {
      if (!window.confirm(t("Discard unsaved transcript edits and use the saved version? Cancel to save edits first."))) return;
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
        if (result.saved) { setMessageName(result.displayName ?? ""); setMessage("Exported {name}."); }
      }
    } catch { setMessage("Could not export the saved transcript."); }
  }

  const activeJob = status?.meetingId === meetingId && ["loading", "running", "cancelling"].includes(status.state);
  const showSetup = !selectedRun || settingsOpen || activeJob || (status?.state === "error" && status.meetingId === meetingId);
  return <section className="document-panel" aria-label={t("Transcript")}>
    <div className="transcript-heading"><div><h2>{t("Transcript by time")}</h2><p>{working.length > 0
      ? t("{count} segments in this recording", { count: working.length })
      : t("Review and correct timestamped speech.")}</p></div>
      {selectedRun && <Button variant="outline" size="sm" aria-expanded={showSetup} onClick={() => setSettingsOpen((open) => !open)}>
        <Settings2 size={16} />{t("Transcription options")}</Button>}
    </div>
    {showSetup && <div className="transcription-setup">
      <div className="document-toolbar"><div className="toolbar-actions">
        <Label htmlFor="speech-language">{t("Speech language")}</Label>
        <NativeSelect id="speech-language" value={language} disabled={activeJob} onChange={(event) => setLanguage(event.target.value)}>
          <option value="vi">{t("Vietnamese (default)")}</option><option value="auto">{t("Auto detect")}</option><option value="en">{t("English")}</option>
        </NativeSelect>
        <Button size="sm" disabled={busy || activeJob || !selectedModel} onClick={() => void startOrRetry(false)}><WandSparkles size={15} /> {t("Transcribe")}</Button>
        {activeJob && <Button variant="secondary" size="sm" onClick={() => void bridgeCall("asr.cancel").catch(() => setMessage("Could not cancel transcription."))}><X size={15} /> {t("Cancel")}</Button>}
        {status?.state === "error" && status.meetingId === meetingId && <Button variant="secondary" size="sm" onClick={() => void startOrRetry(true)}>{t("Retry")}</Button>}
      </div></div>
      <div className="transcription-start">
        <Label htmlFor="transcription-start-time">{t("Start transcription at")}</Label>
        <Input id="transcription-start-time" aria-label={t("Start transcription at")} value={startTime}
          onChange={(event) => setStartTime(event.target.value)} disabled={activeJob} inputMode="numeric" placeholder="00:00" />
        <Button variant="secondary" size="sm" disabled={activeJob || audioDurationSeconds <= 0}
          onClick={() => setStartTime(startTimeLabel(playheadSeconds))}>{t("Use playback position")}</Button>
        <span className="hint">{t("Transcribes from this time to the end of the selected recording.")}</span>
      </div>
      {activeJob && <div className="job-progress"><span>{t(status?.state === "loading" ? "Loading model" : status?.state === "cancelling" ? "Cancelling" : "Transcribing")}</span>
        <Progress value={status?.progress == null ? null : Math.round(status.progress * 100)} aria-label={t("Transcription progress")} /> <span>{status?.progress == null ? "" : `${Math.round(status.progress * 100)}%`}</span></div>}
      {status?.state === "error" && status.meetingId === meetingId && <div className="alert" role="alert">{t(status.error || "Transcription failed.")}</div>}
      <div className="document-toolbar secondary"><Label htmlFor="run-select">{t("Saved run")}</Label>
        <NativeSelect id="run-select" value={selectedRun} onChange={(event) => {
          if (dirty && !window.confirm(t("Discard unsaved transcript edits?"))) return;
          const nextRun = event.target.value;
          if (!nextRun) return;
          const previousRun = selectedRun;
          setSelectedRun(nextRun);
          void bridgeCall("transcript.select", { meetingId, runId: nextRun }).then(onRunChange)
            .catch(() => { setSelectedRun(previousRun); setMessage("Could not select this transcript run."); });
        }}><option value="" disabled={runs.length > 0}>{t("No transcript yet")}</option>
          {runs.map((item) => <option key={item.run_id} value={item.run_id}>{formatDateTime(item.created_at, languageUI)} · {item.model_repository} · {t("from {time}", { time: startTimeLabel(item.start_seconds ?? 0) })}</option>)}
        </NativeSelect></div>
      {!selectedModel && <p className="hint">{t("A local speech model is required. Install one in Models; no cloud fallback is used.")}</p>}
    </div>}
    {working.length === 0 && <div className="empty-document">{t(selectedRun && run
      ? "No speech was detected in this transcription range. Review the selected start time and audio."
      : "No saved transcript for this meeting.")}</div>}
    <div className="segment-list">{working.map((segment, index) => <div className={`segment${playheadSeconds >= segment.start && playheadSeconds < segment.end ? " current" : ""}`} key={segment.id}>
      <Button variant="ghost" className="timestamp-button" onClick={() => onSeek(segment.start)}
        aria-label={t("Play audio from {time}", { time: timestamp(segment.start) })}>
        <CirclePlay size={23} /><span>{timestamp(segment.start)}</span><span aria-hidden="true">– {timestamp(segment.end)}</span></Button>
      <div className="segment-copy"><Textarea rows={1} aria-label={t("Transcript segment {id}", { id: segment.id })} value={segment.text}
        onChange={(event) => setWorking((current) => current.map((item, i) => i === index ? { ...item, text: event.target.value } : item))} />
        {run && segment.text !== run.original[index]?.text && <small>{t("Original ASR:")} {run.original[index]?.text}</small>}
      </div></div>)}</div>
    {working.length > 0 && <p className="transcript-note"><Info size={17} />{t("Select a timestamp to play the matching audio.")}</p>}
    <div className="document-footer"><Button size="sm" disabled={!dirty || busy} onClick={() => void save()}><Save size={15} /> {t("Save edits")}</Button>
      <Button variant="secondary" size="sm" disabled={!selectedRun} onClick={() => void exportText(true)}><Copy size={15} /> {t("Copy saved")}</Button>
      <Button variant="secondary" size="sm" disabled={!selectedRun} onClick={() => void exportText(false)}><Download size={15} /> {t("Export TXT")}</Button>
      {dirty && <span className="dirty-label">{t("Unsaved edits")}</span>}</div>
    {message && <p className="feedback" role="status">{t(message, { name: messageName })}</p>}
  </section>;
}
