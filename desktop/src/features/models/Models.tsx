import { useCallback, useEffect, useState } from "react";
import { Check, Download, HardDriveDownload, Trash2 } from "lucide-react";
import { bridgeCall } from "@/shared/bridge/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

type Choice = {
  name: string; repository: string; publisher: string; license: string;
  estimated_bytes: number; revision: string; resource_warning: string;
};
type Installed = {
  id: string; repository: string; publisher: string; license: string; revision: string; bytes: number;
};
type Catalog = { choices: Choice[]; installed: Installed[]; selectedId: string | null };
type InstallStatus = { jobId: string | null; state: string; stage: string; progress: number | null; modelId: string | null; error: string | null };

function sizeLabel(bytes: number): string { return `${(bytes / 1_000_000).toFixed(0)} MB`; }

export function Models({ backendReady }: { backendReady: boolean }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [status, setStatus] = useState<InstallStatus | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    if (!backendReady) return;
    try { setCatalog(await bridgeCall<Catalog>("model.catalog")); }
    catch { setMessage("Could not read local model installations."); }
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
    if (!window.confirm("Delete this installed model from fahmm? Meeting data will remain.")) return;
    setBusy(true); setMessage("");
    try { await bridgeCall("model.delete", { modelId }); await refresh(); setMessage("Model deleted."); }
    catch { setMessage("Could not delete this model. It may be in use."); }
    finally { setBusy(false); }
  }
  const installing = status?.state === "running";
  return <section className="page models-page" aria-labelledby="models-heading">
    <div className="eyebrow">OFFLINE SPEECH</div><h1 id="models-heading">Models</h1>
    <p>Download a speech model once. Transcription uses installed models locally, including when offline.</p>
    {status && status.state !== "idle" && <Card className="panel model-progress" role="status"><HardDriveDownload size={19} />
      <div><strong>{status.state === "running" ? status.stage : status.state === "completed" ? "Model installed" : "Model installation failed"}</strong>
        {installing && <Progress value={status.progress == null ? null : Math.round(status.progress * 100)} aria-label="Model download progress" />}
        {status.error && <span>{status.error}</span>}</div></Card>}
    {message && <p className="feedback" role="status">{message}</p>}
    <div className="model-section"><h2>Installed models</h2>
      {!catalog?.installed.length && <Card className="panel empty-panel">No local model installed yet. Choose one from the catalog below.</Card>}
      {catalog?.installed.map((model) => <Card className="panel model-card" key={model.id}>
        <div><h3>{catalog.choices.find((choice) => choice.repository === model.repository)?.name || model.repository}</h3>
          <p>{model.repository} · {sizeLabel(model.bytes)} · {model.license}</p></div>
        <div className="model-actions">{catalog.selectedId === model.id ? <Badge variant="outline" className="selected-label"><Check size={15} /> Selected</Badge>
          : <Button variant="secondary" size="sm" disabled={busy} onClick={() => void select(model.id)}>Use model</Button>}
          <Button variant="ghost" size="icon-sm" aria-label={`Delete ${model.repository}`} disabled={busy || installing}
            onClick={() => void remove(model.id)}><Trash2 size={17} /></Button></div>
      </Card>)}</div>
    <div className="model-section"><h2>Reviewed model catalog</h2><p>Downloads are explicit and may use significant disk space.</p>
      {catalog?.choices.map((choice) => {
        const installed = catalog.installed.some((model) => model.repository === choice.repository);
        return <Card className="panel model-card" key={choice.repository}><div><h3>{choice.name}</h3>
          <p>{choice.repository} · about {sizeLabel(choice.estimated_bytes)} · {choice.license}</p>
          {choice.resource_warning && <p className="resource-warning">{choice.resource_warning}</p>}</div>
          <Button variant="outline" size="sm" disabled={busy || installing || installed} onClick={() => void download(choice.repository)}>
            {installed ? <Check size={15} /> : <Download size={15} />}{installed ? "Installed" : "Download"}</Button></Card>;
      })}</div>
  </section>;
}
