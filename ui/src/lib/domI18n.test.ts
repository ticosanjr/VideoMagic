import { describe, expect, it } from "vitest";
import { GLOSSARY } from "./domI18n";

describe("domI18n glossary", () => {
  it("translates the high-traffic panel labels", () => {
    expect(GLOSSARY["Refresh"]).toBe("Atualizar");
    expect(GLOSSARY["Add step"]).toBe("Adicionar etapa");
    expect(GLOSSARY["B-roll approval"]).toBe("Aprovação de B-roll");
    expect(GLOSSARY["Ripple delete"]).toBe("Excluir com ripple");
  });

  it("has no empty or duplicated targets", () => {
    const values = Object.values(GLOSSARY);
    expect(values.every((value) => value.trim().length > 0)).toBe(true);
    expect(new Set(values).size).toBe(values.length);
  });
});
