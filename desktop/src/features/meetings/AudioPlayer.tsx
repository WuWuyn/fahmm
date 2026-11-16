import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import WaveSurfer from "wavesurfer.js";
import { bridgeCall } from "@/shared/bridge/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useUIStore } from "@/shared/uiStore";
import { useT } from "@/shared/i18n";

type Ticket = { ticket: string; contentType: string };
type Peaks = { seconds: number; peaks: number[] };

function mediaUrl(meetingId: string, ticket: string): string {
  return `http://fahmm.localhost/media/${meetingId}/${ticket}`;
}

function timeLabel(value: number): string {
  const seconds = Math.floor(value);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function AudioPlayer({ meetingId, seekTo }: {
  meetingId: string; seekTo: { seconds: number; nonce: number } | null;
}) {
  const t = useT();
  const container = useRef<HTMLDivElement>(null);
  const player = useRef<WaveSurfer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const theme = useUIStore((state) => state.theme);
  const language = useUIStore((state) => state.language);

  useEffect(() => {
    if (!container.current) return;
    let alive = true;
    let fallbackUsed = false;
    let loadSequence = 0;
    setPlaying(false); setPosition(0); setLoading(true); setError("");
    const wave = WaveSurfer.create({
      container: container.current, height: 70, barWidth: 3, barGap: 2, barRadius: 2,
      waveColor: theme === "dark" ? "#54749f" : "#a8c4e9",
      progressColor: theme === "dark" ? "#76adff" : "#1d5fc7",
      cursorColor: theme === "dark" ? "#a9ccff" : "#1d5fc7",
      normalize: false, backend: "MediaElement", dragToSeek: true,
    });
    player.current = wave;
    wave.on("play", () => setPlaying(true));
    wave.on("pause", () => setPlaying(false));
    wave.on("finish", () => setPlaying(false));
    wave.on("timeupdate", (seconds) => setPosition(seconds));
    const load = async (fallback: boolean) => {
      const sequence = ++loadSequence;
      try {
        const [ticket, data] = await Promise.all([
          bridgeCall<Ticket>(fallback ? "media.fallback" : "media.ticket", { meetingId }),
          bridgeCall<Peaks>("media.peaks", { meetingId, bins: 1024 }),
        ]);
        if (!alive) return;
        setDuration(data.seconds);
        const samples = new Float32Array(data.peaks.length * 2);
        data.peaks.forEach((peak, index) => { samples[index * 2] = -peak; samples[index * 2 + 1] = peak; });
        await wave.load(mediaUrl(meetingId, ticket.ticket), [samples], data.seconds);
        if (alive) setLoading(false);
      } catch {
        if (!alive || sequence !== loadSequence) return;
        if (!fallbackUsed) {
          fallbackUsed = true;
          void load(true);
        } else { setError("Audio playback is unavailable. Try reopening this meeting."); setLoading(false); }
      }
    };
    wave.on("error", () => { if (!fallbackUsed) { fallbackUsed = true; void load(true); } });
    void load(false);
    return () => { alive = false; player.current = null; wave.destroy(); };
  }, [meetingId]);

  useEffect(() => {
    player.current?.setOptions({
      waveColor: theme === "dark" ? "#54749f" : "#a8c4e9",
      progressColor: theme === "dark" ? "#76adff" : "#1d5fc7",
      cursorColor: theme === "dark" ? "#a9ccff" : "#1d5fc7",
    });
  }, [theme]);

  useEffect(() => {
    if (seekTo && player.current && duration > 0) {
      player.current.setTime(Math.min(duration, Math.max(0, seekTo.seconds)));
    }
  }, [seekTo, duration]);

  return <Card className="panel audio-panel" aria-label={t("Meeting audio player")}>
    <div className="audio-heading"><div><h2>{language === "vi" ? "Bản ghi âm" : "Recording"}</h2><p>{t("Local playback")}</p></div>
      <span className="audio-time">{timeLabel(position)} / {timeLabel(duration)}</span></div>
    <div ref={container} className="waveform" aria-label={t("Audio waveform; click to seek")} />
    <div className="audio-controls"><Button variant="secondary" size="sm" disabled={loading || !!error} onClick={() => void player.current?.playPause()}>
      {playing ? <Pause size={16} /> : <Play size={16} />} {t(playing ? "Pause" : "Play")}
    </Button><span className="hint">{t(loading ? "Loading waveform…" : "Select a timestamp or click the waveform to seek.")}</span></div>
    {error && <div className="alert" role="alert">{t(error)}</div>}
  </Card>;
}
