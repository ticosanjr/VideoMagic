"""Built-in recipes, split into a catalog and definition modules."""

from __future__ import annotations

from videoflow.engine.recipes import definitions_advanced as _advanced  # noqa: F401
from videoflow.engine.recipes import definitions_footage as _footage  # noqa: F401
from videoflow.engine.recipes import definitions_full_ai_editor as _full_ai_editor  # noqa: F401
from videoflow.engine.recipes import definitions_lamera as _lamera  # noqa: F401
from videoflow.engine.recipes import definitions_opencode as _opencode  # noqa: F401
from videoflow.engine.recipes import definitions_opusclip as _opusclip  # noqa: F401
from videoflow.engine.recipes import definitions_synthetic as _synthetic  # noqa: F401
from videoflow.engine.recipes.catalog import (
    BUILTIN_RECIPES,
    builtin_recipe,
    get_recipe,
    get_recipe_version,
    list_recipe_history,
    list_recipes,
    recipe_history_dir,
    resolve_recipe_paths,
    restore_recipe_version,
    save_user_recipe,
    user_recipes_dir,
)

__all__ = [
    "BUILTIN_RECIPES",
    "builtin_recipe",
    "get_recipe",
    "get_recipe_version",
    "list_recipe_history",
    "list_recipes",
    "recipe_history_dir",
    "resolve_recipe_paths",
    "restore_recipe_version",
    "save_user_recipe",
    "user_recipes_dir",
]
