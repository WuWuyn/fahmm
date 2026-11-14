import { useEffect, useState } from "react";
import { HashRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { AudioLines, ChevronLeft, ChevronRight, ListMusic, Moon, Settings2, Sun, Boxes, RotateCcw } from "lucide-react";
import { Recorder } from "@/features/recorder/Recorder";
import { Meetings } from "@/features/meetings/Meetings";
import { Models } from "@/features/models/Models";
import { Settings } from "@/features/settings/Settings";
import { bridgeStatus, restartBridge } from "@/shared/bridge/client";
import { useUIStore } from "@/shared/uiStore";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";
import { motion, useReducedMotion } from "motion/react";
import "@/styles/App.css";

const areas = [
  { path: "/recorder", label: "Recorder", icon: AudioLines },
  { path: "/meetings", label: "Meetings", icon: ListMusic },
  { path: "/models", label: "Models", icon: Boxes },
  { path: "/settings", label: "Settings", icon: Settings2 },
] as const;

function App() {
  const theme = useUIStore((state) => state.theme);
  const setTheme = useUIStore((state) => state.setTheme);
  const collapsed = useUIStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);
  const [backendReady, setBackendReady] = useState(false);
  const [checking, setChecking] = useState(true);
  const [restarting, setRestarting] = useState(false);
  const [backendEpoch, setBackendEpoch] = useState(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
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
        {!collapsed && <div className="brand">fahmm<span>MEETING WORKSPACE</span></div>}
        <Button variant="ghost" size="icon-sm" className="collapse-button" onClick={toggleSidebar} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}</Button>
      </div>
      <div className="nav-caption">{collapsed ? "" : "WORKSPACE"}</div>
      <nav aria-label="Main navigation">
        {areas.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path}
          aria-label={label} title={collapsed ? label : undefined}
          className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <Icon size={19} strokeWidth={1.8} /><span>{label}</span>
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="local-note"><span className="local-dot" />{!collapsed && <span>Private by default</span>}</div>
        <Button variant="outline" className="theme-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Light mode" : "Dark mode"}>
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          {!collapsed && <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>}
        </Button>
      </div>
    </aside>
    <main className="main-content">
      <header className="topbar"><span className="topbar-label">Desktop workspace</span><Badge variant="outline" className="privacy-badge">Local by default</Badge></header>
      {!checking && !backendReady && <motion.div className="backend-alert" role="alert"
        initial={reducedMotion ? false : { opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18 }}>
        <div><strong>Local backend unavailable</strong><span>Recording and meeting data are temporarily unavailable.</span></div>
        <Button variant="secondary" disabled={restarting} onClick={() => void restart()}><RotateCcw size={16} />{restarting ? "Restarting…" : "Restart backend"}</Button>
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
