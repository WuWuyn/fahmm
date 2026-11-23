import { useCallback, useEffect, useState } from "react";
import { FilePlus2, FolderDown, RefreshCw } from "lucide-react";
import { bridgeCall, exportReport, importReportFile } from "@/shared/bridge/client";
import { useT } from "@/shared/i18n";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ReportModelSummary } from "@/features/reports/ReportModelInfo";

type Model = { id: string; installed: boolean };
type Meeting = { id: string; name: string };
type Report = { state: string; detail: string; progress: number; files: { id: string; name: string }[];
  preview: string; facts: number; warnings: number; metrics: { seconds?: number; tokens_per_second?: number | null } };
const initial: Report = { state: "idle", detail: "", progress: 0, files: [], preview: "", facts: 0, warnings: 0, metrics: {} };

export function Reports({ backendReady }: { backendReady: boolean }) {
  const t = useT();
  const [report, setReport] = useState<Report>(initial);
  const [models, setModels] = useState<Model[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [model, setModel] = useState("qwen3.5:2b-q4_K_M");
  const [meeting, setMeeting] = useState("");
  const [form, setForm] = useState("");
  const [message, setMessage] = useState("");
  const [working, setWorking] = useState(false);
  const busy = working || report.state === "running";

  const refresh = useCallback(async () => {
    if (!backendReady) return;
    try { const data = await bridgeCall<{ report: Report }>("report.status"); setReport(data.report); }
    catch { setMessage(t("Could not read report status.")); }
  }, [backendReady, t]);
  const refreshModels = useCallback(async () => {
    if (!backendReady) return;
    try { const data = await bridgeCall<{ models: Model[] }>("report.models"); setModels(data.models); }
    catch { setMessage(t("Could not connect to local report models. Check Ollama.")); }
  }, [backendReady, t]);
  useEffect(() => {
    if (!backendReady) return;
    void refresh(); void refreshModels();
    void bridgeCall<{ meetings: Meeting[] }>("meeting.list").then((data) => setMeetings(data.meetings)).catch(() => {});
  }, [backendReady, refresh, refreshModels]);
  useEffect(() => {
    if (report.state !== "running") return;
    const timer = window.setInterval(() => { void refresh(); }, 1800);
    return () => window.clearInterval(timer);
  }, [report.state, refresh]);
  useEffect(() => { if (report.detail === "Đã tải model.") void refreshModels(); }, [report.detail, refreshModels]);

  async function action(fn: () => Promise<unknown>, fallback: string) {
    setWorking(true); setMessage("");
    try { await fn(); await refresh(); }
    catch (error) {
      const detail = typeof error === "string" ? error : error instanceof Error ? error.message : "";
      setMessage(detail && !/^[A-Z_]+$/.test(detail) ? detail : t(fallback));
    }
    finally { setWorking(false); }
  }
  const installed = models.find((entry) => entry.id === model)?.installed === true;

  return <section className="page reports-page" aria-labelledby="reports-heading">
    <div className="page-heading"><div><h1 id="reports-heading">{t("Reports")}</h1>
      <p>{t("Combine local documents and saved meeting transcripts into a source-linked report.")}</p></div></div>
    {message && <div className="alert" role="alert">{message}</div>}
    {!backendReady && <div className="alert" role="status">{t("Connect the local backend to create reports.")}</div>}
    <div className="reports-layout">
      <section className="panel report-input" aria-labelledby="report-sources">
        <div className="report-section-heading"><div><h2 id="report-sources">{t("Source documents")}</h2>
          <p>{t("PDF, Word, Excel, TXT or Markdown. Scanned PDFs need OCR first.")}</p></div><span>{report.files.length}</span></div>
        <div className="control-row"><Button variant="outline" disabled={!backendReady || busy} onClick={() => void action(importReportFile, "Could not add document.")}><FilePlus2 size={16} />{t("Add document")}</Button>
          <Button variant="ghost" disabled={!backendReady || busy || !report.files.length} onClick={() => void action(() => bridgeCall("report.clear"), "Could not clear sources.")}>{t("Clear sources")}</Button></div>
        <ul className="report-file-list">{report.files.map((file) => <li key={file.id}>{file.name}</li>)}</ul>
        {!report.files.length && <p className="hint">{t("No sources selected. Add a document or a saved meeting transcript.")}</p>}
        <div className="report-control"><label htmlFor="report-meeting">{t("Add a saved meeting transcript")}</label>
          <div className="report-inline"><NativeSelect id="report-meeting" value={meeting} onChange={(e) => setMeeting(e.target.value)} disabled={!backendReady || busy}>
            <option value="">{t("Choose a meeting")}</option>{meetings.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </NativeSelect><Button variant="secondary" disabled={!meeting || busy} onClick={() => void action(() => bridgeCall("report.addTranscript", { meetingId: meeting }), "Could not add transcript.")}>{t("Add transcript")}</Button></div>
        </div>
        <div className="report-control"><label htmlFor="report-model">{t("Local report model")}</label>
          <div className="report-inline"><NativeSelect id="report-model" value={model} onChange={(e) => setModel(e.target.value)} disabled={busy || !backendReady}>
            {models.length ? models.map((entry) => <option key={entry.id} value={entry.id}>{entry.id} · {t(entry.installed ? "Installed" : "Not installed")}</option>) : <option value={model}>{model}</option>}
          </NativeSelect><Button variant="outline" size="icon" aria-label={t("Refresh models")} disabled={busy || !backendReady} onClick={() => void refreshModels()}><RefreshCw size={16} /></Button></div>
          <ReportModelSummary model={model} />
          {!installed && models.length > 0 && <Button variant="outline" disabled={busy} onClick={() => void action(() => bridgeCall("report.pull", { model }), "Could not download model.")}>{t("Download selected model")}</Button>}
        </div>
        <div className="report-control"><label htmlFor="report-form">{t("Report form notes (optional)")}</label>
          <Textarea id="report-form" value={form} onChange={(e) => setForm(e.target.value)} disabled={busy} placeholder={t("Optional notes to include in the exported report")} />
          <p className="hint">{t("Notes are included in the report; fields currently follow the fixed form.")}</p>
        </div>
        <div className="control-row report-actions"><Button disabled={!backendReady || busy || !installed || !report.files.length} onClick={() => void action(() => bridgeCall("report.start", { model, form }), "Could not start report. Check the model and stop other active Ollama models.")}>{t("Create report")}</Button>
          {report.state === "running" && <Button variant="outline" onClick={() => void action(() => bridgeCall("report.cancel"), "Could not cancel report.")}>{t("Cancel after current section")}</Button>}</div>
        {(report.state === "running" || report.detail) && <div className="report-progress" role="status"><span>{report.detail}</span>{report.state === "running" && <progress max={1} value={report.progress} />}</div>}
      </section>
      <section className="panel report-output" aria-labelledby="report-result">
        <div className="report-section-heading"><div><h2 id="report-result">{t("Report and sources")}</h2>
          <p>{t("Review every claim against its source before using the report.")}</p></div>
          <Button variant="outline" disabled={busy || report.state !== "completed"} onClick={() => void action(exportReport, "Could not export report. Choose an empty folder.")}><FolderDown size={16} />{t("Export")}</Button></div>
        {report.preview ? <><p className="report-meta">{report.facts} {t("sourced facts")} · {report.warnings} {t("warnings")}{report.metrics.seconds != null && ` · ${report.metrics.seconds}s`}</p>
          <pre className="report-preview">{report.preview}</pre></> : <div className="report-empty"><FilePlus2 size={25} /><p>{t("Your report, source quotations and warnings will appear here.")}</p></div>}
        <p className="hint">{t("Export creates Word, Markdown, JSON and Excel files. Existing files are not overwritten.")}</p>
      </section>
    </div>
  </section>;
}
