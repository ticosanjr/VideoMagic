"""Shared canvas layout for built-in recipe groups."""

from __future__ import annotations

from typing import Any


def build_ui(
    groups: list[
        tuple[str, str, str, str, list[list[str]]]
    ],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    layout_groups: list[dict[str, Any]] = []
    y = 80.0
    for group_id, label, description, color, rows in groups:
        columns = max(len(row) for row in rows)
        width = columns * 460.0 + 80.0
        height = len(rows) * 160.0 + 120.0
        members: list[str] = []
        for row_index, row in enumerate(rows):
            for column, node_id in enumerate(row):
                nodes[node_id] = {
                    "x": 80.0 + column * 460.0,
                    "y": y + 80.0 + row_index * 160.0,
                    "expanded": False,
                    "pinned": False,
                    "width": 420,
                }
                members.append(node_id)
        layout_groups.append(
            {
                "id": group_id,
                "label": label,
                "description": description,
                "color": color,
                "x": 80.0,
                "y": y,
                "width": width,
                "height": height,
                "nodes": members,
            }
        )
        y += height + 60.0
    return {
        "version": 1,
        "viewport": {"x": 0.0, "y": 0.0, "zoom": 1.0},
        "nodes": nodes,
        "groups": layout_groups,
    }
