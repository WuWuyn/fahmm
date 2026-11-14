import { create } from "zustand";

type Theme = "dark" | "light";
type UIState = {
  theme: Theme;
  sidebarCollapsed: boolean;
  setTheme: (theme: Theme) => void;
  toggleSidebar: () => void;
};

function initialTheme(): Theme {
  try { return localStorage.getItem("fahmm-theme") === "light" ? "light" : "dark"; }
  catch { return "dark"; }
}

export const useUIStore = create<UIState>((set) => ({
  theme: initialTheme(),
  sidebarCollapsed: false,
  setTheme: (theme) => {
    try { localStorage.setItem("fahmm-theme", theme); } catch { /* memory preference only */ }
    set({ theme });
  },
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
}));
