import { useCallback, useEffect, useState } from "react";
import { AudioLines, FolderOpen, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { AudioPlayer } from "./AudioPlayer";
import { MinutesPanel } from "@/features/minutes/MinutesPanel";
import { TranscriptPanel } from "@/features/transcript/TranscriptPanel";
import { bridgeCall, importAudio } from "@/shared/bridge/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate, formatDateTime, useT } from "@/shared/i18n";
import { useUIStore } from "@/shared/uiStore";

type Meeting = {
  id: string; name: string; created_at: string; source_kind: string;
  recording_state: string; processing_state: string; privacy_mode: string;
};

function timeLabel(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function createdTime(value: string, language: "en" | "vi"): string {
  return new Intl.DateTimeFormat(language === "vi" ? "vi-VN" : "en-US", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export function Meetings({ backendReady }: { backendReady: boolean }) {
  const t = useT();
  const language = useUIStore((state) => state.language);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"transcript" | "minutes">("transcript");
  const [seekTo, setSeekTo] = useState<{ seconds: number; nonce: number; play?: boolean } | null>(null);
  const [playheadSeconds, setPlayheadSeconds] = useState(0);
  const [audioDurationSeconds, setAudioDurationSeconds] = useState(0);
  const [runVersion, setRunVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [cleanup, setCleanup] = useState<{ deletions: string[]; imports: string[] }>({ deletions: [], imports: [] });

  const refreshCleanup = useCallback(async () => {
    if (!backendReady) return;
    try { setCleanup(await bridgeCall("meeting.cleanupList")); }
    catch { setMessage("Could not read storage cleanup state."); }
  }, [backendReady]);

  const refresh = useCallback(async () => {
    if (!backendReady) return;
    try {
      const data = await bridgeCall<{ meetings: Meeting[] }>("meeting.list");
      setMeetings(data.meetings);
      setSelectedId((current) => current && data.meetings.some((item) => item.id === current)
        ? current : data.meetings[0]?.id || "");
    } catch { setMessage("Could not load local meetings. Restart the backend and try again."); }
    finally { setLoading(false); }
  }, [backendReady]);
  useEffect(() => { void refresh(); void refreshCleanup(); }, [refresh, refreshCleanup]);

  async function addMeeting() {
    setMessage("");
    try {
      const result = await importAudio();
      if (result.meetingId) { await refresh(); setSelectedId(result.meetingId); setPlayheadSeconds(0); setAudioDurationSeconds(0); }
    } catch { setMessage("Could not import audio. Choose a supported WAV, MP3, M4A, or FLAC file."); }
  }

  async function deleteMeeting(meeting: Meeting) {
    if (!window.confirm(t("Delete '{name}' and its fahmm audio, transcripts, minutes, and metadata? This cannot be undone. Exports and backups remain.", { name: meeting.name }))) return;
    setMessage("");
    try { await bridgeCall("meeting.delete", { meetingId: meeting.id }); await refresh(); await refreshCleanup();
      setMessage("Meeting data deleted locally."); }
    catch { setMessage("Could not delete this meeting. Close active work and check Storage cleanup."); await refreshCleanup(); }
  }

  async function renameMeeting(meeting: Meeting) {
    const name = window.prompt(t("Meeting name"), meeting.name)?.trim();
    if (!name || name === meeting.name) return;
    try { await bridgeCall("meeting.rename", { meetingId: meeting.id, name });
      await refresh(); setMessage("Meeting renamed locally."); }
    catch { setMessage("Could not rename this meeting."); }
  }

  async function clean(kind: "deletion" | "import", meetingId: string) {
    if (kind === "import" && !window.confirm(t("Clean abandoned import {id}? The original source file remains.", { id: meetingId }))) return;
    try { await bridgeCall(kind === "deletion" ? "meeting.retryCleanup" : "meeting.cleanImport", { meetingId });
      await refreshCleanup(); setMessage(kind === "deletion" ? "Incomplete deletion cleaned." : "Abandoned import cleaned."); }
    catch { setMessage("Storage cleanup could not finish. Release file locks and retry."); await refreshCleanup(); }
  }

  const selected = meetings.find((meeting) => meeting.id === selectedId);
  const handleRunChange = useCallback(() => setRunVersion((version) => version + 1), []);
  const visibleMeetings = meetings.filter((meeting) => meeting.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const today = new Date().toDateString();
  const groups = [
    { label: t("Today"), items: visibleMeetings.filter((meeting) => new Date(meeting.created_at).toDateString() === today) },
    { label: t("Earlier"), items: visibleMeetings.filter((meeting) => new Date(meeting.created_at).toDateString() !== today) },
  ];
  const statusLabel = (meeting: Meeting) => {
    if (meeting.recording_state !== "completed") return t("Recording needs attention");
    if (meeting.processing_state === "completed") return t("Transcript ready");
    if (meeting.processing_state === "running") return t("Transcribing…");
    if (["error", "cancelled"].includes(meeting.processing_state)) return t("Transcription needs attention");
    return t("Not transcribed yet");
  };
  const seek = (seconds: number) => setSeekTo({ seconds, nonce: Date.now(), play: true });
  return <section className="page meetings-page" aria-labelledby="meetings-heading">
    <div className="meetings-layout"><aside className="meeting-list" aria-label={t("Saved meetings")}>
      <div className="meeting-list-header"><h1 id="meetings-heading">{t("Meetings")}</h1><span className="count-badge">{meetings.length}</span></div>
      <Button variant="outline" className="meeting-import" disabled={!backendReady} onClick={() => void addMeeting()}><Plus size={19} /> {t("Import audio")}</Button>
      <div className="meeting-search"><Search size={18} aria-hidden="true" /><Input aria-label={t("Search meetings")} placeholder={t("Search meetings…")}
        value={query} onChange={(event) => setQuery(event.target.value)} /></div>
      {!backendReady && meetings.length === 0 && <p>{t("Connect the local backend to load meetings.")}</p>}
      {backendReady && loading && <p>{t("Loading meetings…")}</p>}
      {backendReady && !loading && meetings.length === 0 && <div className="library-empty"><FolderOpen size={26} /><p>{t("No meetings yet. Record or import audio to begin.")}</p></div>}
      {backendReady && !loading && meetings.length > 0 && visibleMeetings.length === 0 &&
        <p className="meeting-search-empty">{t("No meetings match your search.")}</p>}
      {groups.map((group) => group.items.length > 0 && <div className="meeting-group" key={group.label}>
        <h2>{group.label}</h2>
        {group.items.map((meeting) => <button key={meeting.id} className={`meeting-row${meeting.id === selectedId ? " selected" : ""}`}
          aria-current={meeting.id === selectedId ? "true" : undefined}
          onClick={() => { setSelectedId(meeting.id); setTab("transcript"); setSeekTo(null); setPlayheadSeconds(0); setAudioDurationSeconds(0); }}>
          <span className="meeting-icon"><AudioLines size={20} /></span><span className="meeting-row-copy"><strong>{meeting.name}</strong>
            <small>{group.label === t("Today") ? createdTime(meeting.created_at, language) : formatDate(meeting.created_at, language)} · {t(meeting.source_kind)}</small>
            <small className="meeting-row-status">{statusLabel(meeting)}</small></span>
        </button>)}
      </div>)}
    </aside>
    <div className="meeting-detail">{message && <div className="alert" role="alert">{t(message)}</div>}{selected ? <>
      <div className="detail-title"><div className="detail-title-copy"><div className="detail-name"><h2>{selected.name}</h2>
          <Button variant="ghost" size="icon-sm" aria-label={t("Rename {name}", { name: selected.name })} onClick={() => void renameMeeting(selected)}><Pencil size={18} /></Button></div>
        <p>{formatDateTime(selected.created_at, language)} · {t(selected.source_kind)}{audioDurationSeconds > 0 && <> · {timeLabel(audioDurationSeconds)}</>}</p></div>
        <div className="detail-actions"><Badge variant="outline" className={`privacy-badge${selected.privacy_mode === "cloud_permitted" ? " cloud" : ""}`}>{t(selected.privacy_mode === "cloud_permitted" ? "Cloud Allowed" : "Local Only")}</Badge>
          <DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline" size="icon-sm" aria-label={t("More meeting actions")}><MoreHorizontal size={19} /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => void renameMeeting(selected)}><Pencil size={15} />{t("Rename meeting")}</DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={() => void deleteMeeting(selected)}><Trash2 size={15} />{t("Delete meeting")}</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
        </div></div>
      {selected.recording_state === "completed" ? <AudioPlayer meetingId={selected.id} seekTo={seekTo}
          onPositionChange={setPlayheadSeconds} onDurationChange={setAudioDurationSeconds} />
        : <div className="panel audio-panel">{t("Recover or finish this recording before playback.")}</div>}
      <Tabs value={tab} onValueChange={(value) => setTab(value as "transcript" | "minutes")}>
        <TabsList variant="line" className="document-tabs" aria-label={t("Meeting documents")}>
          <TabsTrigger value="transcript">{t("Transcript")}</TabsTrigger>
          <TabsTrigger value="minutes">{t("Minutes")}</TabsTrigger>
        </TabsList>
        <TabsContent value="transcript" className="panel document-surface"><TranscriptPanel meetingId={selected.id} onSeek={seek}
          playheadSeconds={playheadSeconds} audioDurationSeconds={audioDurationSeconds}
          onRunChange={handleRunChange} /></TabsContent>
        <TabsContent value="minutes" className="panel document-surface"><MinutesPanel meetingId={selected.id} privacyMode={selected.privacy_mode}
            onPrivacyChange={(mode) => setMeetings((current) => current.map((item) => item.id === selected.id ? { ...item, privacy_mode: mode } : item))}
            onSeek={seek} onOpenSource={(runId, seconds) => {
              void bridgeCall("transcript.select", { meetingId: selected.id, runId })
                .then(() => { seek(seconds); setTab("transcript"); setRunVersion((version) => version + 1); })
                .catch(() => setMessage("Could not open the source transcript."));
            }} runVersion={runVersion} /></TabsContent>
      </Tabs>
    </> : <div className="panel detail-empty">{t("Select a meeting to review its recording and documents.")}</div>}</div></div>
    {(cleanup.deletions.length > 0 || cleanup.imports.length > 0) && <Card className="panel recovery-panel" aria-label={t("Storage cleanup")}>
      <h2>{t("Storage cleanup")}</h2><p>{t("Retry an interrupted deletion or remove an abandoned import copy.")}</p>
      {cleanup.deletions.map((id) => <div className="recovery-item" key={id}><span>{t("Incomplete deletion {id}", { id: id.slice(0, 8) })}</span>
        <Button variant="secondary" onClick={() => void clean("deletion", id)}>{t("Retry cleanup")}</Button></div>)}
      {cleanup.imports.map((id) => <div className="recovery-item" key={id}><span>{t("Abandoned import {id}", { id: id.slice(0, 8) })}</span>
        <Button variant="secondary" onClick={() => void clean("import", id)}>{t("Clean import")}</Button></div>)}
    </Card>}
  </section>;
}
