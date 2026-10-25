import type { RecipeSummary } from "./api";

export type RecipeFilter = "favorites" | "recent" | "all";

export function recipesFor(
  recipes: RecipeSummary[],
  filter: RecipeFilter,
  query: string,
  recentLimit = 6
): RecipeSummary[] {
  const needle = query.trim().toLocaleLowerCase();
  const matches = (recipe: RecipeSummary) =>
    !needle ||
    recipe.name.toLocaleLowerCase().includes(needle) ||
    recipe.description.toLocaleLowerCase().includes(needle) ||
    recipe.id.toLocaleLowerCase().includes(needle) ||
    (recipe.tags ?? []).some((tag) => tag.toLocaleLowerCase().includes(needle));

  if (filter === "favorites") {
    return recipes
      .filter((recipe) => Boolean(recipe.favorite) && matches(recipe))
      .sort((left, right) => left.name.localeCompare(right.name));
  }
  if (filter === "recent") {
    return recipes
      .filter((recipe) => Boolean(recipe.last_used_at) && matches(recipe))
      .sort((left, right) =>
        String(right.last_used_at).localeCompare(String(left.last_used_at))
      )
      .slice(0, recentLimit);
  }
  return recipes
    .filter(matches)
    .sort((left, right) => {
      if (left.favorite !== right.favorite) return left.favorite ? -1 : 1;
      return left.name.localeCompare(right.name);
    });
}
