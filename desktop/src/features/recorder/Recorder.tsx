import { useCallback, useEffect, useState } from "react";
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

const emptySnapshot: Snapshot = { state: "idle", seconds: 0, meetingId: null, error: null, skippedChunks: 0, levels: { system: 0, microphone: 0 } };

function timeLabel(seconds: number): string {
  const total = Math.floor(seconds);
  return `${String(Math.floor(total / 3600)).padStart(2, "0")}:${String(Math.floor(total / 60) % 60).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
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

  const refresh = useCallback(async () => {
    if (!backendReady) return;
    try {
      const [nextSnapshot, pending] = await Promise.all([
        bridgeCall<Snapshot>("recording.snapshot"),
        bridgeCall<{ meetings: Incomplete[] }>("recording.incomplete"),
      ]);
      setSnapshot({ ...nextSnapshot, levels: nextSnapshot.levels ?? { system: 0, microphone: 0 } });
      setIncomplete(pending.meetings);
    } catch { setError("Could not read the recorder state. Restart the backend and try again."); }
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

  useEffect(() => { void refresh(); void refreshDevices(); }, [refresh, refreshDevices]);
  useEffect(() => {
    if (!backendReady) return;
    const timer = window.setInterval(() => { void refresh(); }, 750);
    return () => window.clearInterval(timer);
  }, [backendReady, refresh]);

  async function action(operation: string, params: Record<string, unknown> = {}) {
    setBusy(true);
    setError("");
    try {
      await bridgeCall(operation, params);
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
        </Card>
      </div>
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
