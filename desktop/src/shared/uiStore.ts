import { create } from "zustand";

type Theme = "dark" | "light";
export type Language = "en" | "vi";
type UIState = {
  theme: Theme;
  language: Language;
  sidebarCollapsed: boolean;
  setTheme: (theme: Theme) => void;
  setLanguage: (language: Language) => void;
  toggleSidebar: () => void;
};

function initialTheme(): Theme {
  try { return localStorage.getItem("fahmm-theme") === "light" ? "light" : "dark"; }
  catch { return "dark"; }
}

function initialLanguage(): Language {
  try { return localStorage.getItem("fahmm-language") === "vi" ? "vi" : "en"; }
  catch { return "en"; }
}

export const useUIStore = create<UIState>((set) => ({
  theme: initialTheme(),
  language: initialLanguage(),
  sidebarCollapsed: false,
  setTheme: (theme) => {
    try { localStorage.setItem("fahmm-theme", theme); } catch { /* memory preference only */ }
    set({ theme });
  },
  setLanguage: (language) => {
    try { localStorage.setItem("fahmm-language", language); } catch { /* memory preference only */ }
    set({ language });
  },
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
}));
