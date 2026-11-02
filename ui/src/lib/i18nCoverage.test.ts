import { describe, expect, it } from "vitest";
import { GLOSSARY } from "./glossary";

const files = import.meta.glob("/src/**/*.svelte", {
  query: "?raw",
  import: "default",
  eager: true
}) as Record<string, string>;

function visibleStrings(source: string): string[] {
  const found: string[] = [];
  const pattern = />\s*([A-Za-z][^<>{}\n]{2,80}?)\s*</g;
  for (const match of source.matchAll(pattern)) {
    const value = match[1].trim();
    if (
      value &&
      !value.startsWith("http") &&
      !value.startsWith("/") &&
      !value.startsWith(".") &&
      !/[$\\{]/.test(value)
    ) {
      found.push(value);
    }
  }
  return found;
}

describe("i18n coverage", () => {
  it("translates every visible static string", () => {
    const missing = new Set<string>();
    for (const source of Object.values(files)) {
      for (const value of visibleStrings(source)) {
        if (!(value in GLOSSARY)) missing.add(value);
      }
    }
    expect([...missing].sort()).toEqual([]);
  });

  it("keeps the shared navigation table aligned with the glossary", () => {
    expect(GLOSSARY["Assistant"]).toBe("Assistente");
    expect(GLOSSARY["Doctor / diagnostics"]).toBe("Diagnóstico / doctor");
  });
});
