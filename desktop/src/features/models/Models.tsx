import { useCallback, useEffect, useState } from "react";
import { Check, Download, HardDriveDownload, Trash2 } from "lucide-react";
import { bridgeCall } from "@/shared/bridge/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useT } from "@/shared/i18n";
import { ReportModelComparison } from "@/features/reports/ReportModelInfo";

type Choice = {
  name: string; repository: string; publisher: string; license: string;
  estimated_bytes: number; revision: string; resource_warning: string;
};
type Installed = {
  id: string; repository: string; publisher: string; license: string; revision: string; bytes: number;
};
type Catalog = { choices: Choice[]; installed: Installed[]; selectedId: string | null };
type InstallStatus = { jobId: string | null; state: string; stage: string; progress: number | null; modelId: string | null; error: string | null };
type LocalAI = { connected: boolean; models: string[]; selectedModel: string; ready: boolean };
type LocalJob = { state: string; progress: number; error: string | null; versionId: string | null };

function sizeLabel(bytes: number): string { return `${(bytes / 1_000_000).toFixed(0)} MB`; }

export function Models({ backendReady }: { backendReady: boolean }) {
  const t = useT();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [status, setStatus] = useState<InstallStatus | null>(null);
  const [localAI, setLocalAI] = useState<LocalAI | null>(null);
  const [localDownload, setLocalDownload] = useState<LocalJob | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    if (!backendReady) return;
    try { setCatalog(await bridgeCall<Catalog>("model.catalog")); }
    catch { setMessage("Could not read local model installations."); }
    try { setLocalAI(await bridgeCall<LocalAI>("llm.availability")); }
    catch { setLocalAI(null); }
  }, [backendReady]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!backendReady) return;
    const poll = () => { void bridgeCall<InstallStatus>("model.installStatus").then((next) => {
      setStatus((prior) => {
        if (next.state === "completed" && prior?.state !== "completed") void refresh();
        return next;
      });
    }).catch(() => undefined); };
    poll(); const timer = window.setInterval(poll, 1000);
    return () => window.clearInterval(timer);
  }, [backendReady, refresh]);
  useEffect(() => {
    if (!backendReady) return;
    const poll = () => { void bridgeCall<LocalJob>("llm.pullStatus").then((next) => {
      setLocalDownload((prior) => {
        if (next.state === "completed" && prior?.state === "running") void refresh();
        return next;
      });
    }).catch(() => undefined); };
    poll(); const timer = window.setInterval(poll, 1200);
    return () => window.clearInterval(timer);
  }, [backendReady, refresh]);

  async function download(repository: string) {
    setBusy(true); setMessage("");
    try { await bridgeCall("model.install", { repository }); setMessage("Model download started."); }
    catch { setMessage("Could not start the model download."); }
    finally { setBusy(false); }
  }
  async function select(modelId: string) {
    setBusy(true); setMessage("");
    try { await bridgeCall("model.select", { modelId }); await refresh(); setMessage("Local model selected."); }
    catch { setMessage("Could not select this installation."); }
    finally { setBusy(false); }
  }
  async function remove(modelId: string) {
    if (!window.confirm(t("Delete this installed model from fahmm? Meeting data will remain."))) return;
    setBusy(true); setMessage("");
    try { await bridgeCall("model.delete", { modelId }); await refresh(); setMessage("Model deleted."); }
    catch { setMessage("Could not delete this model. It may be in use."); }
    finally { setBusy(false); }
  }
  async function pullLocalAI() {
    setMessage("");
    try { await bridgeCall("llm.pullStart"); setMessage("Local language model download started."); }
    catch { setMessage("Start Ollama before downloading the language model."); }
  }
  async function selectLocalAI(model: string) {
    setMessage("");
    try { await bridgeCall("llm.select", { model }); await refresh(); setMessage("Local language model selected."); }
    catch { setMessage("Could not select the local language model."); }
  }
  const installing = status?.state === "running";
  return <section className="page models-page" aria-labelledby="models-heading">
    <div className="eyebrow">{t("OFFLINE SPEECH")}</div><h1 id="models-heading">{t("Models")}</h1>
    <p>{t("Download a speech model once. Transcription uses installed models locally, including when offline.")}</p>
    <ReportModelComparison />
    <div className="model-section local-ai-section"><h2>{t("Local AI for meeting minutes")}</h2>
      <p>{t("Speech models transcribe audio. Ollama uses a separate language model to write the DENSO meeting-minutes form on this computer.")}</p>
      {!localAI?.connected ? <Card className="panel model-card"><div><h3>Ollama</h3>
        <p>{t("Install and start Ollama for Windows, then return here to download the language model.")}</p></div>
        <a href="https://ollama.com/download/windows" target="_blank" rel="noreferrer">{t("Download Ollama")}</a></Card>
        : <>
          <Card className="panel model-card"><div><h3>Qwen3 4B Instruct</h3>
            <p>qwen3:4b-instruct · {t("about")} 2.5 GB · Apache 2.0</p>
            <p>{t("Vietnamese capable; runs locally through Ollama. On 4 GB VRAM, it may also use system memory.")}</p></div>
            <Button variant="outline" size="sm" disabled={localDownload?.state === "running" || localAI.models.includes("qwen3:4b-instruct")}
              onClick={() => void pullLocalAI()}><Download size={15} />{t(localAI.models.includes("qwen3:4b-instruct") ? "Installed" : "Download")}</Button>
          </Card>
          {localDownload?.state === "running" && <Card className="panel model-progress" role="status">
            <span>{t("Downloading local language model…")}</span>
            <Progress value={Math.round(localDownload.progress * 100)} aria-label={t("Language model download progress")} /></Card>}
          {localDownload?.state === "failed" && <p className="feedback" role="alert">{localDownload.error}</p>}
          {localAI.models.length > 0 && <div className="model-card panel"><div><h3>{t("Language model for minutes")}</h3>
            <p>{t("Choose an installed Ollama model. The selected model writes the existing meeting minutes form.")}</p></div>
            <select aria-label={t("Language model for minutes")} value={localAI.selectedModel} onChange={(event) => void selectLocalAI(event.target.value)}>
              {!localAI.models.includes(localAI.selectedModel) && <option value={localAI.selectedModel}>{localAI.selectedModel}</option>}
              {localAI.models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select></div>}
        </>}
    </div>
    {status && status.state !== "idle" && <Card className="panel model-progress" role="status"><HardDriveDownload size={19} />
      <div><strong>{t(status.state === "running" ? status.stage : status.state === "completed" ? "Model installed" : "Model installation failed")}</strong>
        {installing && <Progress value={status.progress == null ? null : Math.round(status.progress * 100)} aria-label={t("Model download progress")} />}
        {status.error && <span>{t(status.error)}</span>}</div></Card>}
    {message && <p className="feedback" role="status">{t(message)}</p>}
    <div className="model-section"><h2>{t("Installed models")}</h2>
      {!catalog?.installed.length && <Card className="panel empty-panel">{t("No local model installed yet. Choose one from the catalog below.")}</Card>}
      {catalog?.installed.map((model) => <Card className="panel model-card" key={model.id}>
        <div><h3>{t(catalog.choices.find((choice) => choice.repository === model.repository)?.name || model.repository)}</h3>
          <p>{model.repository} · {sizeLabel(model.bytes)} · {model.license}</p></div>
        <div className="model-actions">{catalog.selectedId === model.id ? <Badge variant="outline" className="selected-label"><Check size={15} /> {t("Selected")}</Badge>
          : <Button variant="secondary" size="sm" disabled={busy} onClick={() => void select(model.id)}>{t("Use model")}</Button>}
          <Button variant="ghost" size="icon-sm" aria-label={t("Delete {name}", { name: model.repository })} disabled={busy || installing}
            onClick={() => void remove(model.id)}><Trash2 size={17} /></Button></div>
      </Card>)}</div>
    <div className="model-section"><h2>{t("Reviewed model catalog")}</h2><p>{t("Downloads are explicit and may use significant disk space.")}</p>
      {catalog?.choices.map((choice) => {
        const installed = catalog.installed.some((model) => model.repository === choice.repository);
        return <Card className="panel model-card" key={choice.repository}><div><h3>{t(choice.name)}</h3>
          <p>{choice.repository} · {t("about")} {sizeLabel(choice.estimated_bytes)} · {choice.license}</p>
          {choice.resource_warning && <p className="resource-warning">{t(choice.resource_warning)}</p>}</div>
          <Button variant="outline" size="sm" disabled={busy || installing || installed} onClick={() => void download(choice.repository)}>
            {installed ? <Check size={15} /> : <Download size={15} />}{t(installed ? "Installed" : "Download")}</Button></Card>;
      })}</div>
  </section>;
}
