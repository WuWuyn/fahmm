import { useEffect, useRef, useState } from "react";
import { Pause, Play, Volume2, VolumeX } from "lucide-react";
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

export function AudioPlayer({ meetingId, seekTo, onPositionChange, onDurationChange }: {
  meetingId: string; seekTo: { seconds: number; nonce: number; play?: boolean } | null;
  onPositionChange?: (seconds: number) => void; onDurationChange?: (seconds: number) => void;
}) {
  const t = useT();
  const container = useRef<HTMLDivElement>(null);
  const player = useRef<WaveSurfer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const theme = useUIStore((state) => state.theme);
  const language = useUIStore((state) => state.language);

  useEffect(() => {
    if (!container.current) return;
    let alive = true;
    let fallbackUsed = false;
    let loadSequence = 0;
    setPlaying(false); setPosition(0); onPositionChange?.(0); setDuration(0); onDurationChange?.(0);
    setLoading(true); setError("");
    const wave = WaveSurfer.create({
      container: container.current, height: 48, barWidth: 3, barGap: 2, barRadius: 2,
      waveColor: theme === "dark" ? "#5c82ac" : "#a8c4e9",
      progressColor: theme === "dark" ? "#80b5ff" : "#1d5fc7",
      cursorColor: theme === "dark" ? "#a9ccff" : "#1d5fc7",
      normalize: false, backend: "MediaElement", dragToSeek: true,
    });
    player.current = wave;
    wave.setPlaybackRate(speed);
    wave.setMuted(muted);
    wave.on("play", () => setPlaying(true));
    wave.on("pause", () => setPlaying(false));
    wave.on("finish", () => setPlaying(false));
    wave.on("timeupdate", (seconds) => { setPosition(seconds); onPositionChange?.(seconds); });
    const load = async (fallback: boolean) => {
      const sequence = ++loadSequence;
      try {
        const [ticket, data] = await Promise.all([
          bridgeCall<Ticket>(fallback ? "media.fallback" : "media.ticket", { meetingId }),
          bridgeCall<Peaks>("media.peaks", { meetingId, bins: 1024 }),
        ]);
        if (!alive) return;
        setDuration(data.seconds); onDurationChange?.(data.seconds);
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
      waveColor: theme === "dark" ? "#5c82ac" : "#a8c4e9",
      progressColor: theme === "dark" ? "#80b5ff" : "#1d5fc7",
      cursorColor: theme === "dark" ? "#a9ccff" : "#1d5fc7",
    });
  }, [theme]);

  useEffect(() => { player.current?.setPlaybackRate(speed); }, [speed]);
  useEffect(() => { player.current?.setMuted(muted); }, [muted]);

  useEffect(() => {
    if (seekTo && player.current && duration > 0) {
      player.current.setTime(Math.min(duration, Math.max(0, seekTo.seconds)));
      if (seekTo.play) void player.current.play().catch(() => setError("Audio playback is unavailable. Try reopening this meeting."));
    }
  }, [seekTo, duration]);

  return <Card className="panel audio-panel" aria-label={t("Meeting audio player")}>
    <div className="audio-heading"><h2>{language === "vi" ? "Bản ghi âm" : "Recording"}</h2></div>
    <div className="audio-playback"><Button className="audio-play-button" disabled={loading || !!error}
      aria-label={t(playing ? "Pause" : "Play")} onClick={() => void player.current?.playPause()}>
      {playing ? <Pause size={21} fill="currentColor" /> : <Play size={21} fill="currentColor" />}
    </Button><div className="audio-wave-area"><div ref={container} className="waveform" aria-label={t("Audio waveform; click to seek")} />
      <div className="audio-ticks" aria-hidden="true">{[0, 1, 2, 3].map((tick) => <span key={tick}>{timeLabel(duration * tick / 3)}</span>)}</div></div></div>
    <div className="audio-controls"><span className="audio-time">{timeLabel(position)} / {timeLabel(duration)}</span>
      <div className="audio-control-actions"><select aria-label={t("Playback speed")} value={speed}
        onChange={(event) => setSpeed(Number(event.target.value))}>
        {[0.75, 1, 1.25, 1.5, 2].map((value) => <option key={value} value={value}>{value}×</option>)}
      </select><Button variant="ghost" size="icon-sm" aria-label={t(muted ? "Unmute audio" : "Mute audio")}
        onClick={() => setMuted((current) => !current)}>{muted ? <VolumeX size={19} /> : <Volume2 size={19} />}</Button></div></div>
    {loading && <span className="hint">{t("Loading waveform…")}</span>}
    {error && <div className="alert" role="alert">{t(error)}</div>}
  </Card>;
}
