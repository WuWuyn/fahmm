import { useT } from "@/shared/i18n";
import { useUIStore } from "@/shared/uiStore";

type ReportModelInfo = {
  id: string;
  name: string;
  size: number;
  speed: number;
  facts: number;
  purpose: string;
  limitation: string;
};

export const REPORT_MODEL_INFO: ReportModelInfo[] = [
  {
    id: "qwen3.5:2b-q4_K_M", name: "Lite — Qwen3.5 2B", size: 1.9, speed: 9.67, facts: 4,
    purpose: "Fast and lightweight; useful for previews and sorting documents.",
    limitation: "Review for missing details before using the result.",
  },
  {
    id: "qwen3:4b-instruct-2507-q4_K_M", name: "Standard — Qwen3 4B Instruct", size: 2.5, speed: 5.67, facts: 7,
    purpose: "Suggested to try for the main report and structured fields.",
    limitation: "Slower than Lite in the earlier trial; review the output.",
  },
  {
    id: "qwen3.5:4b-q4_K_M", name: "Pro — Qwen3.5 4B", size: 3.3, speed: 4.77, facts: 4,
    purpose: "An option to explore more difficult reports.",
    limitation: "Larger and slower in the earlier trial; needs more testing.",
  },
];

function useNumberFormatter() {
  const language = useUIStore((state) => state.language);
  return (value: number) => new Intl.NumberFormat(language === "vi" ? "vi-VN" : "en-US", {
    maximumFractionDigits: 2,
  }).format(value);
}

export function ReportModelSummary({ model }: { model: string }) {
  const t = useT();
  const number = useNumberFormatter();
  const info = REPORT_MODEL_INFO.find((item) => item.id === model);
  if (!info) return null;
  return <div className="report-model-summary" aria-live="polite">
    <strong>{info.name}</strong>
    <p>{t(info.purpose)} {t(info.limitation)}</p>
    <p>{t("Approx. {size} GB · {speed} tokens/sec in an earlier CPU trial", {
      size: number(info.size), speed: number(info.speed),
    })}</p>
    <a href="#/models">{t("Compare the three report models")}</a>
  </div>;
}

export function ReportModelComparison() {
  const t = useT();
  const number = useNumberFormatter();
  return <section className="model-section report-comparison" aria-labelledby="report-models-heading">
    <div className="report-comparison-heading"><div><h2 id="report-models-heading">{t("Compare report models")}</h2>
      <p>{t("Choose the report model in Reports. Meeting-minutes models are managed separately below.")}</p></div>
      <a className="report-open-link" href="#/reports">{t("Open Reports")}</a></div>
    <div className="report-comparison-table-wrap">
      <table className="report-comparison-table">
        <caption className="sr-only">{t("Report model measurements from the earlier trial")}</caption>
        <thead><tr><th scope="col">{t("Measure")}</th>{REPORT_MODEL_INFO.map((item) => <th scope="col" key={item.id}>{item.name}</th>)}</tr></thead>
        <tbody>
          <tr><th scope="row">{t("Download size")}</th>{REPORT_MODEL_INFO.map((item) => <td key={item.id}>{number(item.size)} GB</td>)}</tr>
          <tr><th scope="row">{t("CPU speed")}</th>{REPORT_MODEL_INFO.map((item) => <td key={item.id}>{number(item.speed)} {t("tokens/sec")}</td>)}</tr>
          <tr><th scope="row">{t("Facts retained")}</th>{REPORT_MODEL_INFO.map((item) => <td key={item.id}>{item.facts}</td>)}</tr>
        </tbody>
      </table>
    </div>
    <div className="report-model-notes">{REPORT_MODEL_INFO.map((item) => <div key={item.id}>
      <h3>{item.name}{item.name.startsWith("Standard") && <span>{t("Suggested to try")}</span>}</h3>
      <p>{t(item.purpose)} {t(item.limitation)}</p>
    </div>)}</div>
    <p className="report-comparison-caveat">{t("Earlier prototype trial: one short Vietnamese report; six documents were skipped for low RAM. Retained facts are not an accuracy score, and current results may differ. Form and table quality still need evaluation.")}</p>
    <p className="report-comparison-caveat">{t("On an 8 GB computer, available memory matters; Lite has the smallest download, but all models need enough free RAM.")}</p>
  </section>;
}
