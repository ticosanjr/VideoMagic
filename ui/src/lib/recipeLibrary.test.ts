import { describe, expect, it } from "vitest";
import { recipesFor } from "./recipeLibrary";
import type { RecipeSummary } from "./api";

const base = { description: "", source: "builtin", use_count: 0, tags: [] };
const recipes: RecipeSummary[] = [
  {
    ...base,
    id: "recent",
    name: "Recent",
    favorite: false,
    last_used_at: "2026-01-02T10:00:00+00:00"
  },
  {
    ...base,
    id: "favorite",
    name: "Favorite",
    favorite: true,
    last_used_at: "2026-01-01T10:00:00+00:00"
  },
  {
    ...base,
    id: "unused",
    name: "Unused",
    favorite: false,
    last_used_at: ""
  }
];

describe("recipesFor", () => {
  it("filters favorites and recent recipes", () => {
    expect(recipesFor(recipes, "favorites", "").map((item) => item.id)).toEqual([
      "favorite"
    ]);
    expect(recipesFor(recipes, "recent", "").map((item) => item.id)).toEqual([
      "recent",
      "favorite"
    ]);
  });

  it("searches and sorts all recipes with favorites first", () => {
    expect(recipesFor(recipes, "all", "fav").map((item) => item.id)).toEqual([
      "favorite"
    ]);
    expect(recipesFor(recipes, "all", "").map((item) => item.id)).toEqual([
      "favorite",
      "recent",
      "unused"
    ]);
  });
});
