"""Compatibility shim for the canonical brand kit module."""

from __future__ import annotations

from videoflow.application.brand_kit import (
    BrandTemplate,
    apply_brand_options,
    delete_template,
    get_template,
    list_templates,
    save_template,
    templates_dir,
)

__all__ = ["BrandTemplate", "apply_brand_options", "delete_template",
           "get_template", "list_templates", "save_template", "templates_dir"]
