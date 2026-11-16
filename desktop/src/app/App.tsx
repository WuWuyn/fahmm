import { useEffect, useState } from "react";
import { HashRouter, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AudioLines, ChevronDown, ChevronLeft, ChevronRight, ListMusic, LockKeyhole, Moon, Settings2, Sun, Boxes, RotateCcw } from "lucide-react";
import { Recorder } from "@/features/recorder/Recorder";
import { Meetings } from "@/features/meetings/Meetings";
import { Models } from "@/features/models/Models";
import { Settings } from "@/features/settings/Settings";
import { bridgeStatus, restartBridge } from "@/shared/bridge/client";
import { useUIStore } from "@/shared/uiStore";
import { useT } from "@/shared/i18n";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { motion, useReducedMotion } from "motion/react";
import "@/styles/App.css";

const areas = [
  { path: "/recorder", label: "Recorder", icon: AudioLines },
  { path: "/meetings", label: "Meetings", icon: ListMusic },
  { path: "/models", label: "Models", icon: Boxes },
  { path: "/settings", label: "Settings", icon: Settings2 },
] as const;

function Topbar({ language, setLanguage }: { language: "en" | "vi"; setLanguage: (language: "en" | "vi") => void }) {
  const t = useT();
  const location = useLocation();
  const current = areas.find((area) => area.path === location.pathname);
  return <header className="topbar">
    <div className="topbar-path"><span>{t("Workspace")}</span><span aria-hidden="true">/</span><strong>{t(current?.label ?? "Recorder")}</strong></div>
    <div className="topbar-actions"><span className="topbar-privacy"><LockKeyhole size={17} />{t("Local by default")}</span>
      <Button variant="outline" size="sm" className="language-button" type="button"
        aria-label={t(language === "en" ? "Switch to Vietnamese" : "Switch to English")}
        title={t(language === "en" ? "Switch to Vietnamese" : "Switch to English")}
        onClick={() => setLanguage(language === "en" ? "vi" : "en")}>
        <span>{language === "vi" ? "Tiếng Việt" : "English"}</span><ChevronDown size={16} />
      </Button></div>
  </header>;
}

function App() {
  const t = useT();
  const theme = useUIStore((state) => state.theme);
  const setTheme = useUIStore((state) => state.setTheme);
  const language = useUIStore((state) => state.language);
  const setLanguage = useUIStore((state) => state.setLanguage);
  const collapsed = useUIStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);
  const [backendReady, setBackendReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [restarting, setRestarting] = useState(false);
  const [backendEpoch, setBackendEpoch] = useState(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  useEffect(() => {
    let current = true;
    let pending = false;
    const check = async () => {
      if (pending) return;
      pending = true;
      const ready = await bridgeStatus();
      if (current) { setBackendReady(ready); setChecking(false); }
      pending = false;
    };
    void check();
    const timer = window.setInterval(() => { void check(); }, 3000);
    return () => { current = false; window.clearInterval(timer); };
  }, []);

  async function restart() {
    setRestarting(true);
    try { await restartBridge(); setBackendReady(await bridgeStatus()); setBackendEpoch((epoch) => epoch + 1); }
    catch { setBackendReady(false); }
    finally { setRestarting(false); }
  }

  return <TooltipProvider><HashRouter><div className={`app-shell ${collapsed ? "collapsed" : ""}`}>
    <aside className="sidebar">
      <div className="brand-row"><div className="brand-symbol"><AudioLines size={21} /></div>
        {!collapsed && <div className="brand">fahmm<span>{t("MEETING WORKSPACE")}</span></div>}
        <Button variant="ghost" size="icon-sm" className="collapse-button" onClick={toggleSidebar} aria-label={t(collapsed ? "Expand sidebar" : "Collapse sidebar")}
          title={t(collapsed ? "Expand sidebar" : "Collapse sidebar")}>{collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}</Button>
      </div>
      <div className="nav-caption">{collapsed ? "" : t("WORKSPACE")}</div>
      <nav aria-label={t("Main navigation")}>
        {areas.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path}
          aria-label={t(label)} title={collapsed ? t(label) : undefined}
          className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <Icon size={19} strokeWidth={1.8} /><span>{t(label)}</span>
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="local-note"><span className="local-dot" />{!collapsed && <span>{t("Private by default")}</span>}</div>
        <Button variant="outline" className="theme-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={t(theme === "dark" ? "Switch to light mode" : "Switch to dark mode")}
          title={t(theme === "dark" ? "Light mode" : "Dark mode")}>
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          {!collapsed && <span>{t(theme === "dark" ? "Light mode" : "Dark mode")}</span>}
        </Button>
      </div>
    </aside>
    <main className="main-content">
      <Topbar language={language} setLanguage={setLanguage} />
      {!checking && !backendReady && <motion.div className="backend-alert" role="alert"
        initial={reducedMotion ? false : { opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18 }}>
        <div><strong>{t("Local backend unavailable")}</strong><span>{t("Recording and meeting data are temporarily unavailable.")}</span></div>
        <Button variant="secondary" disabled={restarting} onClick={() => void restart()}><RotateCcw size={16} />{t(restarting ? "Restarting…" : "Restart backend")}</Button>
      </motion.div>}
      <Routes>
        <Route path="/" element={<Navigate to="/recorder" replace />} />
        <Route path="/recorder" element={<Recorder key={backendEpoch} backendReady={backendReady} />} />
        <Route path="/meetings" element={<Meetings key={backendEpoch} backendReady={backendReady} />} />
        <Route path="/models" element={<Models key={backendEpoch} backendReady={backendReady} />} />
        <Route path="/settings" element={<Settings key={backendEpoch} backendReady={backendReady} />} />
      </Routes>
    </main>
  </div></HashRouter></TooltipProvider>;
}

export default App;
