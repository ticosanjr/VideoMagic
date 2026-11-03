import { afterEach, describe, expect, it, vi } from "vitest";
import { validateRecipe } from "./api";

describe("validateRecipe", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("scopes validation to a named step", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true, recipe: {}, order: ["ingest"] }), {
        status: 200,
        headers: { "content-type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);
    await validateRecipe({ id: "demo", steps: [] } as never, "edit");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/recipes/validate?through=edit");
    expect(init.method).toBe("POST");
  });
});
