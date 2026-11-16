import { useCallback } from "react";
import { type Language, useUIStore } from "./uiStore";
import { vi } from "./vi";

type Values = Record<string, string | number>;

export function translate(language: Language, english: string, values: Values = {}): string {
  const template = language === "vi" ? vi[english] ?? english : english;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match);
}

export function useT() {
  const language = useUIStore((state) => state.language);
  return useCallback((english: string, values?: Values) => translate(language, english, values), [language]);
}

export function formatDate(value: string, language: Language): string {
  return new Date(value).toLocaleDateString(language === "vi" ? "vi-VN" : undefined);
}

export function formatDateTime(value: string, language: Language): string {
  return new Date(value).toLocaleString(language === "vi" ? "vi-VN" : undefined);
}
