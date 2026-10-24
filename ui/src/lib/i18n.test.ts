import { describe, expect, it } from "vitest";
import { locales, t } from "./i18n";

describe("i18n", () => {
  it("translates the shell in English and Portuguese", () => {
    expect(t("en", "jobs")).toBe("Jobs");
    expect(t("pt-BR", "jobs")).toBe("Tarefas");
    expect(t("pt-BR", "activity")).toBe("Atividade");
    expect(t("pt-BR", "notifications")).toBe("Notificações");
  });

  it("falls back to English for an unknown locale", () => {
    expect(t("xx", "shortcuts")).toBe("Keyboard shortcuts");
  });

  it("returns the key when no translation exists", () => {
    expect(t("en", "missing.key")).toBe("missing.key");
  });

  it("lists both locales", () => {
    expect(locales().sort()).toEqual(["en", "pt-BR"]);
  });
});
