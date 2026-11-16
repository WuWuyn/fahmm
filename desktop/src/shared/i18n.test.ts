// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { translate } from "./i18n";

beforeEach(() => { localStorage.clear(); });

describe("interface language", () => {
  it("restores a saved Vietnamese choice and falls back to English for an invalid value", async () => {
    localStorage.setItem("fahmm-language", "vi");
    vi.resetModules();
    const vietnamese = await import("./uiStore");
    expect(vietnamese.useUIStore.getState().language).toBe("vi");

    localStorage.setItem("fahmm-language", "other");
    vi.resetModules();
    const english = await import("./uiStore");
    expect(english.useUIStore.getState().language).toBe("en");
  });

  it("translates interface copy while keeping user names unchanged", () => {
    expect(translate("vi", "Delete {name}", { name: "Project Atlas" })).toBe("Xóa Project Atlas");
    expect(translate("en", "Delete {name}", { name: "Project Atlas" })).toBe("Delete Project Atlas");
    expect(translate("vi", "Project Atlas")).toBe("Project Atlas");
  });
});
