import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type AudioDragEvent =
  | { type: "enter" | "over"; x: number; y: number }
  | { type: "leave" }
  | { type: "drop"; x: number; y: number; token?: number; error?: string };

export async function bridgeCall<T>(operation: string, params: Record<string, unknown> = {}): Promise<T> {
  if (!isTauri()) throw new Error("Desktop backend is available only in the Tauri app");
  return invoke<T>("bridge_call", { operation, params });
}

export async function bridgeStatus(): Promise<boolean> {
  if (!isTauri()) return false;
  try {
    await invoke("bridge_status");
    return true;
  } catch {
    return false;
  }
}

export async function restartBridge(): Promise<void> {
  await invoke("bridge_restart");
}

export async function importAudio(): Promise<{ cancelled?: boolean; meetingId?: string }> {
  return invoke("bridge_import");
}

export async function listenAudioDrag(handler: (event: AudioDragEvent) => void): Promise<UnlistenFn | null> {
  if (!isTauri()) return null;
  return listen<AudioDragEvent>("fahmm://audio-drag", (event) => handler(event.payload));
}

export async function importDroppedAudio(token: number): Promise<{ meetingId: string }> {
  return invoke("bridge_import_dropped", { token });
}

export async function discardDroppedAudio(token: number): Promise<void> {
  await invoke("bridge_discard_dropped", { token });
}

export async function demoAudioAvailable(): Promise<boolean> {
  if (!isTauri()) return false;
  const result = await invoke<{ available: boolean }>("bridge_demo_status");
  return result.available;
}

export async function importDemoAudio(): Promise<{ meetingId: string }> {
  return invoke("bridge_import_demo");
}

export async function exportSaved(
  meetingId: string, documentId: string, documentKind: "minutes" | "minutesWord" | "transcript" | "transcriptPlain",
): Promise<{ cancelled?: boolean; saved?: boolean; displayName?: string }> {
  return invoke("bridge_export", { meetingId, documentId, documentKind });
}

export async function exportAudio(meetingId: string): Promise<{ cancelled?: boolean; saved?: boolean; displayName?: string }> {
  return invoke("bridge_export_audio", { meetingId });
}

export async function importReportFile(): Promise<{ cancelled?: boolean }> {
  return invoke("bridge_report_import");
}

export async function exportReport(): Promise<{ cancelled?: boolean; saved?: boolean }> {
  return invoke("bridge_report_export");
}
