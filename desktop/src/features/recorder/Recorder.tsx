import { useCallback, useEffect, useRef, useState } from "react";
import { Circle, Pause, Play, RotateCcw, Square } from "lucide-react";
import { bridgeCall } from "@/shared/bridge/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Progress } from "@/components/ui/progress";
import { formatDateTime, useT } from "@/shared/i18n";
import { useUIStore } from "@/shared/uiStore";

type Device = { id: string; name: string };
type Devices = { system: Device[]; microphone: Device[] };
type Snapshot = {
  state: string; seconds: number; meetingId: string | null; error: string | null; skippedChunks: number;
  levels: { system: number; microphone: number };
};
type Incomplete = { id: string; name: string; createdAt: string };
type InstalledModel = { id: string; repository: string };
type ModelCatalog = { installed: InstalledModel[]; selectedId: string | null };
type LiveStatus = {
  state: string; meetingId: string | null; runId: string | null; cursorSeconds: number;
  segmentCount: number; provisionalCount: number; reviewWindows: number; errorCode: string | null;
  captureStatus: string | null; backlogSeconds: number | null;
};
type LiveRun = { runId: string; state: string; cursorSeconds?: number; modelId?: string; errorCode?: string | null };
type Hypothesis = { id: number; start: number; end: number; text: string; source: "system" | "microphone"; status: "committed" | "matched" | "provisional" };

const activeLiveStates = new Set(["starting", "running", "cancelling"]);
const resumableLiveStates = new Set(["new", "running", "cancelled"]);
const resumableLiveErrors = new Set(["live_worker_crash", "live_resource_busy", "live_capture_failed", "live_failed", "cuda_driver", "cuda_runtime", "cuda_cublas", "cuda_cudnn", "cuda_compute", "cuda_vram", "cuda_failed", "cuda_worker_crash"]);
const liveErrors: Record<string, string> = {
  live_audio_gap: "Audio has a gap. Review or recover the recording before retrying.",
  live_source_missing: "A recording source is missing. Review or recover the recording before retrying.",
  live_capture_failed: "Recording needs recovery before live transcription can continue.",
  live_audio_changed: "The recording changed. This saved live progress cannot be resumed safely.",
  live_model_changed: "The saved speech model has changed or is unavailable.",
  live_resource_busy: "The recording or speech model is being changed. Try again shortly.",
  cuda_runtime: "CUDA libraries are missing or incompatible. Check cuBLAS and cuDNN.",
  cuda_cublas: "CUDA could not load cuBLAS (cublas64_12.dll) or a required dependency.",
  cuda_cudnn: "CUDA could not load cuDNN (cudnn64_9.dll) or a required dependency.",
  cuda_driver: "CUDA could not access a compatible NVIDIA GPU or driver.",
  cuda_compute: "This GPU does not support the selected CUDA compute type.",
  cuda_vram: "CUDA ran out of GPU memory. Try a smaller model or free GPU memory.",
};

const emptySnapshot: Snapshot = { state: "idle", seconds: 0, meetingId: null, error: null, skippedChunks: 0, levels: { system: 0, microphone: 0 } };

function timeLabel(seconds: number): string {
  const total = Math.floor(seconds);
  return `${String(Math.floor(total / 3600)).padStart(2, "0")}:${String(Math.floor(total / 60) % 60).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function liveStateLabel(state: string): string {
  switch (state) {
    case "starting": return "Starting live transcription";
    case "running": return "Live transcription running";
    case "cancelling": return "Stopping live transcription";
    case "cancelled": return "Live transcription stopped";
    case "needs_review": return "Live transcription needs review";
    case "completed": return "Live processing finished; review required";
    case "error": return "Live transcription stopped with an error";
    case "new": return "Saved live progress";
    case "unreadable": return "Saved live progress cannot be read";
    default: return "Live transcription is not running";
  }
}

function isResourceBusy(error: unknown): boolean {
  if (typeof error === "string") return error.includes("RESOURCE_BUSY");
  if (error instanceof Error) return error.message.includes("RESOURCE_BUSY");
  return !!error && typeof error === "object" && "code" in error && error.code === "RESOURCE_BUSY";
}

function LivePanel({ meetingId, recorderState, enabled, backendReady, selectedModel, starting, startError, pendingRunId, onSeen, onStart }: {
  meetingId: string; recorderState: string; enabled: boolean; backendReady: boolean;
  selectedModel: string; starting: boolean; startError: string; pendingRunId: string | null;
  onSeen: (meetingId: string, runId: string) => void; onStart: (meetingId: string, modelId: string) => void;
}) {
  const t = useT();
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [statusAvailable, setStatusAvailable] = useState(false);
  const [runs, setRuns] = useState<LiveRun[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState("");
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [message, setMessage] = useState("");
  const [readError, setReadError] = useState("");
  const [busy, setBusy] = useState(false);
  const statusSequence = useRef(0);
  const runsSequence = useRef(0);
  const activeRun = useRef("");

  const refreshStatus = useCallback(async () => {
    const sequence = ++statusSequence.current;
    try {
      const next = await bridgeCall<LiveStatus>("live.status");
      if (sequence !== statusSequence.current) return;
      setStatus(next); setStatusAvailable(true);
    } catch {
      if (sequence === statusSequence.current) setStatusAvailable(false);
    }
  }, []);
  useEffect(() => {
    if (!backendReady) return;
    let alive = true;
    let timer = 0;
    const poll = async () => { await refreshStatus(); if (alive) timer = window.setTimeout(() => void poll(), 1000); };
    void poll();
    return () => { alive = false; window.clearTimeout(timer); statusSequence.current += 1; };
  }, [backendReady, refreshStatus]);

  const ownActive = status?.meetingId === meetingId && activeLiveStates.has(status.state);
  const otherActive = !!status?.meetingId && status.meetingId !== meetingId && activeLiveStates.has(status.state);
  const show = enabled || ownActive;
  const refreshRuns = useCallback(async (after = "") => {
    const sequence = ++runsSequence.current;
    try {
      const page = await bridgeCall<{ runs: LiveRun[]; nextCursor: string | null }>("live.runs", { meetingId, after, limit: 50 });
      if (sequence !== runsSequence.current) return;
      setRuns((previous) => after ? [...previous, ...page.runs.filter((item) => !previous.some((old) => old.runId === item.runId))] : page.runs);
      setNextCursor(page.nextCursor);
      setSelectedRun((current) => current || page.runs[0]?.runId || "");
      setMessage((current) => current === "Could not load saved live progress." ? "" : current);
    } catch {
      if (sequence === runsSequence.current) setMessage("Could not load saved live progress.");
    }
  }, [meetingId]);
  useEffect(() => {
    if (!backendReady || !show) return;
    void refreshRuns();
    return () => { runsSequence.current += 1; };
  }, [backendReady, show, status?.state, status?.runId, refreshRuns]);
  useEffect(() => {
    if (ownActive && status?.runId && activeRun.current !== status.runId) {
      activeRun.current = status.runId;
      setSelectedRun(status.runId);
    }
  }, [ownActive, status?.runId]);
  useEffect(() => {
    if (pendingRunId && status?.meetingId === meetingId && status.runId === pendingRunId) onSeen(meetingId, pendingRunId);
  }, [pendingRunId, status?.meetingId, status?.runId, meetingId, onSeen]);
  useEffect(() => {
    if (!ownActive) setMessage((current) => current === "Stopping live transcription. Recording continues." ? "" : current);
  }, [ownActive]);
  useEffect(() => {
    setHypotheses([]); setReadError("");
    if (!backendReady || !show || !selectedRun) return;
    let alive = true;
    let sequence = 0;
    let timer = 0;
    const read = async () => {
      const request = ++sequence;
      try {
        const page = await bridgeCall<{ items: Hypothesis[] }>("live.read", { meetingId, runId: selectedRun, kind: "hypotheses", after: 0, limit: 30, latest: true });
        if (alive && request === sequence) { setHypotheses(page.items); setReadError(""); }
      } catch {
        if (alive && request === sequence && !ownActive) setReadError("Could not read this saved live progress.");
      }
      if (alive) timer = window.setTimeout(() => void read(), 1200);
    };
    void read();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [backendReady, show, meetingId, selectedRun, ownActive]);

  async function stopLive() {
    if (!status?.runId || status.meetingId !== meetingId || busy) return;
    setBusy(true); setMessage("");
    try {
      const result = await bridgeCall<{ accepted: boolean }>("live.cancel", { meetingId, runId: status.runId });
      setMessage(result.accepted ? "Stopping live transcription. Recording continues." : "The live task changed. Check its current status.");
      await refreshStatus();
    } catch { setMessage("Could not stop live transcription. Recording continues."); }
    finally { setBusy(false); }
  }
  async function resumeLive() {
    if (!selectedRun || busy) return;
    setBusy(true); setMessage("");
    try {
      await bridgeCall("live.resume", { meetingId, runId: selectedRun });
      await refreshStatus();
    } catch (error) { setMessage(isResourceBusy(error) ? "Wait for the current transcription or AI job to finish." : "Could not resume live transcription. Check the recording and selected model."); }
    finally { setBusy(false); }
  }
  if (!show) return null;
  const selected = runs.find((item) => item.runId === selectedRun);
  const resumable = !!selected && (resumableLiveStates.has(selected.state) ||
    (selected.state === "error" && !!selected.errorCode && resumableLiveErrors.has(selected.errorCode)));
  const canResume = resumable && !ownActive && !otherActive && statusAvailable && recorderState !== "error";
  const canStart = enabled && !!selectedModel && ["starting", "recording", "paused"].includes(recorderState) && !ownActive && !otherActive && statusAvailable;
  const relevantStatus = status?.meetingId === meetingId ? status : null;
  const errorText = relevantStatus?.errorCode ? liveErrors[relevantStatus.errorCode] || "Live transcription stopped. Check the recording and speech model." : "";
  return <section className="panel mt-4 min-w-0 space-y-3 p-5 sm:p-6" aria-labelledby="live-heading">
    <div><h2 id="live-heading">{t("Live transcription (experimental)")}</h2>
      <p className="text-sm text-muted-foreground">{t("Words may be missing or repeated. This is not a finished transcript or meeting minutes.")}</p></div>
    {!statusAvailable && <p className="text-sm text-muted-foreground" role="status">{t("Could not check live transcription. Recording continues.")}</p>}
    {otherActive && <p className="text-sm text-muted-foreground" role="status">{t("A live transcription for another meeting is running.")}</p>}
    {relevantStatus && <div role="status" aria-live="polite">
      <strong>{t(liveStateLabel(relevantStatus.state))}</strong>
      {relevantStatus.backlogSeconds != null && Number.isFinite(relevantStatus.backlogSeconds) && <p className="text-sm text-muted-foreground">{t("Approx. {time} awaiting transcription", { time: timeLabel(Math.max(0, relevantStatus.backlogSeconds)) })}</p>}
      {(relevantStatus.provisionalCount > 0 || relevantStatus.reviewWindows > 0) && <p className="text-sm text-muted-foreground">{t("Some words need review against the recording.")}</p>}
    </div>}
    {(message || startError || errorText) && <p className="feedback" role="alert">{t(message || startError || errorText)}</p>}
    <div className="flex flex-wrap gap-2">
      {canStart && <Button variant="secondary" size="sm" disabled={busy || starting} onClick={() => onStart(meetingId, selectedModel)}>{t("Start live transcription")}</Button>}
      {ownActive && <Button variant="secondary" size="sm" disabled={busy || status?.state === "cancelling"} onClick={() => void stopLive()}>{t("Stop live transcription")}</Button>}
    </div>
    {(runs.length > 0 || selectedRun) && <div className="space-y-2">
      <Label htmlFor="live-checkpoint">{t("Saved live progress")}</Label>
      <NativeSelect id="live-checkpoint" value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
        {selectedRun && !runs.some((item) => item.runId === selectedRun) && <option value={selectedRun}>{t("Current live task")}</option>}
        {runs.map((item, index) => <option key={item.runId} value={item.runId}>{t("Checkpoint {number}: {state}", { number: index + 1, state: t(liveStateLabel(item.state)) })}</option>)}
      </NativeSelect>
      {nextCursor && <Button variant="ghost" size="sm" disabled={busy} onClick={() => void refreshRuns(nextCursor)}>{t("Load more saved progress")}</Button>}
      {canResume && <Button variant="secondary" size="sm" disabled={busy || starting} onClick={() => void resumeLive()}>{t("Resume live progress")}</Button>}
      {selected?.state === "error" && <p className="text-sm text-muted-foreground">{t(selected.errorCode && liveErrors[selected.errorCode] || "Resolve the recording or speech model error before retrying.")}</p>}
    </div>}
    {readError && <p className="text-sm text-muted-foreground" role="status">{t(readError)}</p>}
    {selectedRun && <div><h3>{t("Recent live words")}</h3>
      {hypotheses.length === 0 ? !readError && <p className="text-sm text-muted-foreground">{t("No live words saved yet.")}</p> : <ol className="mt-2 max-h-72 space-y-2 overflow-y-auto">
        {[...hypotheses].sort((first, second) => first.start - second.start || first.end - second.end || first.id - second.id).map((item) => <li key={item.id} className="min-w-0 break-words text-sm">
          <span className="text-muted-foreground">{timeLabel(item.start)} · {t(item.source === "system" ? "System audio" : "Microphone")} · {t(item.status === "provisional" ? "Tentative" : item.status === "matched" ? "Repeated observation" : "Stored, review needed")}</span>
          <p>{item.text}</p>
        </li>)}
      </ol>}
    </div>}
  </section>;
}

export function Recorder({ backendReady }: { backendReady: boolean }) {
  const t = useT();
  const language = useUIStore((state) => state.language);
  const [devices, setDevices] = useState<Devices>({ system: [], microphone: [] });
  const [systemId, setSystemId] = useState("");
  const [microphoneId, setMicrophoneId] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot>(emptySnapshot);
  const [incomplete, setIncomplete] = useState<Incomplete[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [liveEnabled, setLiveEnabled] = useState(false);
  const [models, setModels] = useState<InstalledModel[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [liveLanguage, setLiveLanguage] = useState("vi");
  const [modelError, setModelError] = useState("");
  const [liveStarting, setLiveStarting] = useState<string | null>(null);
  const [liveStarted, setLiveStarted] = useState<{ meetingId: string; runId: string } | null>(null);
  const [liveStartError, setLiveStartError] = useState<{ meetingId: string; message: string } | null>(null);
  const refreshSequence = useRef(0);
  const mounted = useRef(true);
  const liveStartPending = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; refreshSequence.current += 1; };
  }, []);
  useEffect(() => {
    if (!backendReady || !liveEnabled) return;
    let alive = true;
    void bridgeCall<ModelCatalog>("model.catalog").then((catalog) => {
      if (!alive) return;
      setModels(catalog.installed);
      setSelectedModel((current) => catalog.installed.some((model) => model.id === current) ? current :
        catalog.installed.find((model) => model.id === catalog.selectedId)?.id || catalog.installed[0]?.id || "");
      setModelError("");
    }).catch(() => { if (alive) { setModels([]); setSelectedModel(""); setModelError("Could not load installed speech models."); } });
    return () => { alive = false; };
  }, [backendReady, liveEnabled]);

  const refresh = useCallback(async () => {
    if (!backendReady) return;
    const sequence = ++refreshSequence.current;
    try {
      const [nextSnapshot, pending] = await Promise.all([
        bridgeCall<Snapshot>("recording.snapshot"),
        bridgeCall<{ meetings: Incomplete[] }>("recording.incomplete"),
      ]);
      if (mounted.current && sequence === refreshSequence.current) {
        setSnapshot({ ...nextSnapshot, levels: nextSnapshot.levels ?? { system: 0, microphone: 0 } });
        setIncomplete(pending.meetings);
      }
    } catch { if (mounted.current && sequence === refreshSequence.current) setError("Could not read the recorder state. Restart the backend and try again."); }
  }, [backendReady]);

  const refreshDevices = useCallback(async () => {
    if (!backendReady) return;
    try {
      const next = await bridgeCall<Devices>("recording.devices");
      setDevices(next);
      setSystemId((current) => next.system.some((device) => device.id === current) ? current : next.system[0]?.id || "");
      setMicrophoneId((current) => next.microphone.some((device) => device.id === current) ? current : next.microphone[0]?.id || "");
    } catch { setError("Audio devices could not be listed. Check Windows audio settings."); }
  }, [backendReady]);

  useEffect(() => { void refreshDevices(); }, [refreshDevices]);
  useEffect(() => {
    if (!backendReady) return;
    let alive = true;
    let timer = 0;
    const poll = async () => { await refresh(); if (alive) timer = window.setTimeout(() => void poll(), 750); };
    void poll();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [backendReady, refresh]);

  async function startLive(meetingId: string, modelId: string, language: string) {
    if (liveStartPending.current) return;
    liveStartPending.current = true;
    setLiveStarting(meetingId); setLiveStartError(null);
    try {
      const result = await bridgeCall<{ runId: string }>("live.start", { meetingId, modelId, language });
      if (mounted.current) setLiveStarted({ meetingId, runId: result.runId });
    }
    catch (error) { if (mounted.current) setLiveStartError({ meetingId, message: isResourceBusy(error)
      ? "Wait for the current transcription or AI job to finish. Recording continues."
      : "Could not start live transcription. Check the speech model or wait for other AI and transcription tasks. Recording continues." }); }
    finally { liveStartPending.current = false; if (mounted.current) setLiveStarting(null); }
  }

  const clearLiveStarted = useCallback((meetingId: string, runId: string) => {
    setLiveStarted((current) => current?.meetingId === meetingId && current.runId === runId ? null : current);
  }, []);

  async function action(operation: string, params: Record<string, unknown> = {}) {
    setBusy(true);
    setError("");
    try {
      const result = await bridgeCall<{ meetingId?: string }>(operation, params);
      if (operation === "recording.start" && result?.meetingId) {
        const meetingId = result.meetingId;
        refreshSequence.current += 1;
        setSnapshot((previous) => ({ ...previous, state: "starting", meetingId, seconds: 0, error: null }));
        setLiveStartError(null);
        if (liveEnabled && selectedModel) void startLive(meetingId, selectedModel, liveLanguage);
        else if (liveEnabled) setLiveStartError({ meetingId, message: "Choose an installed speech model to start live transcription. Recording continues." });
      }
      await refresh();
    } catch { setError("Could not change the recording. Check the selected devices and try again."); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, button, [contenteditable=true]")) return;
      if (event.ctrlKey && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "r"
          && snapshot.state === "idle" && backendReady && !busy && systemId && microphoneId) {
        event.preventDefault(); void action("recording.start", { systemId, microphoneId });
      } else if (event.ctrlKey && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "s"
                 && ["recording", "paused"].includes(snapshot.state) && !busy) {
        event.preventDefault(); void action("recording.stop");
      } else if (event.code === "Space" && !event.ctrlKey && !event.altKey && !event.shiftKey
                 && ["recording", "paused"].includes(snapshot.state) && !busy) {
        event.preventDefault(); void action(snapshot.state === "recording" ? "recording.pause" : "recording.resume");
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  });

  const active = ["starting", "recording", "paused", "finalizing"].includes(snapshot.state);
  return (
    <section className="page recorder-page" aria-labelledby="recorder-heading">
      <div className="page-heading">
        <div><div className="eyebrow">{t("CAPTURE")}</div><h1 id="recorder-heading">{t("Recorder")}</h1>
          <p>{t("Capture system audio and your microphone into one local meeting.")}</p></div>
        <Badge variant="outline" className="privacy-badge">{t("Local Only")}</Badge>
      </div>
      <div className="recorder-grid">
        <Card className="panel recording-panel">
          <div className="recording-state" role="status" aria-live="polite">
            <span className={`state-dot ${snapshot.state === "recording" ? "pulsing" : ""}`} />
            {t(snapshot.state === "recording" ? "Recording" : snapshot.state === "paused" ? "Paused" :
              snapshot.state === "finalizing" ? "Finishing" : snapshot.state === "completed" ? "Saved" :
                snapshot.state === "error" ? "Needs attention" : "Ready to record")}
          </div>
          <div className="recording-clock" aria-label={t("Elapsed time {time}", { time: timeLabel(snapshot.seconds) })}>{timeLabel(snapshot.seconds)}</div>
          <div className="live-levels" aria-label={t("Live input levels")}>
            {(["system", "microphone"] as const).map((source) => <div className="live-level" key={source}>
              <div><span>{t(source === "system" ? "System audio" : "Microphone")}</span><span>{Math.round(snapshot.levels[source] * 100)}%</span></div>
              <Progress value={Math.round(snapshot.levels[source] * 100)} aria-label={t("{source} input level", { source: t(source === "system" ? "System audio" : "Microphone") })} />
            </div>)}
            {!active && <p className="hint">{t("Input levels appear while recording.")}</p>}
          </div>
          <div className="control-row">
            {!active && <Button disabled={busy || !backendReady || !systemId || !microphoneId}
              onClick={() => void action("recording.start", { systemId, microphoneId })}>
              <Circle size={17} fill="currentColor" /> {t("Record")}
            </Button>}
            {snapshot.state === "recording" && <Button variant="secondary" disabled={busy} onClick={() => void action("recording.pause")}><Pause size={17} /> {t("Pause")}</Button>}
            {snapshot.state === "paused" && <Button variant="secondary" disabled={busy} onClick={() => void action("recording.resume")}><Play size={17} /> {t("Resume")}</Button>}
            {["recording", "paused", "starting"].includes(snapshot.state) && <Button variant="destructive" disabled={busy} onClick={() => void action("recording.stop")}><Square size={16} fill="currentColor" /> {t("Stop")}</Button>}
          </div>
          {snapshot.state === "completed" && snapshot.meetingId && <Button asChild variant="secondary" size="sm">
            <a href={`#/meetings?open=${encodeURIComponent(snapshot.meetingId)}`}>{t("Open saved meeting")}</a>
          </Button>}
          {(error || snapshot.error) && <div className="alert" role="alert">{t(error || snapshot.error || "")}</div>}
          {snapshot.skippedChunks > 0 && <p className="hint">{t("{count} damaged audio chunk(s) were skipped during recovery.", { count: snapshot.skippedChunks })}</p>}
        </Card>
        <Card className="panel device-panel">
          <div className="panel-heading"><h2>{t("Audio sources")}</h2><Button variant="ghost" size="icon-sm" aria-label={t("Refresh audio devices")} onClick={() => void refreshDevices()}><RotateCcw size={17} /></Button></div>
          <Label htmlFor="system-device">{t("System audio")}</Label>
          <NativeSelect id="system-device" value={systemId} disabled={active} onChange={(event) => setSystemId(event.target.value)}>
            {devices.system.length === 0 && <option value="">{t("No system audio device")}</option>}
            {devices.system.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}
          </NativeSelect>
          <Label htmlFor="microphone-device">{t("Microphone")}</Label>
          <NativeSelect id="microphone-device" value={microphoneId} disabled={active} onChange={(event) => setMicrophoneId(event.target.value)}>
            {devices.microphone.length === 0 && <option value="">{t("No microphone")}</option>}
            {devices.microphone.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}
          </NativeSelect>
          <p className="hint">{t("Windows default devices are listed first. If the microphone meter stays at 0% while you speak, select another microphone and record again.")}</p>
          <p className="hint">{t("Device access begins only after you press Record.")}</p>
          <div className="mt-4 space-y-2 border-t pt-4">
            <label htmlFor="live-enabled" className="flex items-start gap-2 text-sm">
              <input id="live-enabled" type="checkbox" checked={liveEnabled} onChange={(event) => setLiveEnabled(event.target.checked)} aria-describedby="live-option-note" />
              <span>{t("Start live transcription when recording begins (experimental)")}</span>
            </label>
            <p id="live-option-note" className="text-sm text-muted-foreground">{t("Runs locally. Recording continues if live transcription stops or fails.")}</p>
            {liveEnabled && <>
              <Label htmlFor="live-model" className="pt-2">{t("Speech model for live transcription")}</Label>
              <NativeSelect id="live-model" value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} disabled={models.length === 0}>
                {models.length === 0 && <option value="">{t("No installed speech model")}</option>}
                {models.map((model) => <option key={model.id} value={model.id}>{model.repository}</option>)}
              </NativeSelect>
              <Label htmlFor="live-language" className="pt-2">{t("Live transcription language")}</Label>
              <NativeSelect id="live-language" value={liveLanguage} onChange={(event) => setLiveLanguage(event.target.value)}>
                <option value="vi">{t("Vietnamese")}</option>
                <option value="en">{t("English")}</option>
                <option value="auto">{t("Auto detect")}</option>
              </NativeSelect>
              {liveLanguage === "auto" && <p className="text-sm text-muted-foreground">{t("Language is detected separately for each window and may change between windows.")}</p>}
              <p className="text-sm text-muted-foreground">{t("The model and language apply when starting a new live task.")}</p>
              {(modelError || models.length === 0) && <p className="text-sm text-muted-foreground" role="status">{t(modelError || "Install a speech model in Models to use live transcription.")}</p>}
            </>}
          </div>
        </Card>
      </div>
      {snapshot.meetingId && <LivePanel key={snapshot.meetingId} meetingId={snapshot.meetingId} recorderState={snapshot.state}
        enabled={liveEnabled} backendReady={backendReady} selectedModel={selectedModel} starting={liveStarting === snapshot.meetingId || liveStarted?.meetingId === snapshot.meetingId}
        pendingRunId={liveStarted?.meetingId === snapshot.meetingId ? liveStarted.runId : null} onSeen={clearLiveStarted}
        startError={liveStartError?.meetingId === snapshot.meetingId ? liveStartError.message : ""} onStart={(meetingId, modelId) => void startLive(meetingId, modelId, liveLanguage)} />}
      {incomplete.length > 0 && <Card className="panel recovery-panel" aria-labelledby="recovery-heading">
        <h2 id="recovery-heading">{t("Recover recordings")}</h2>
        <p>{t("These sessions have saved audio chunks from an earlier interruption.")}</p>
        {incomplete.map((meeting) => <div className="recovery-item" key={meeting.id}>
          <div><strong>{meeting.name}</strong><small>{formatDateTime(meeting.createdAt, language)}</small></div>
          <Button variant="secondary" disabled={busy || active} onClick={() => void action("recording.recover", { meetingId: meeting.id })}>{t("Recover")}</Button>
        </div>)}
      </Card>}
    </section>
  );
}
