"""Safe variable and expression resolution for recipe parameters."""

from __future__ import annotations

import ast
import re
from typing import Any

_EXPR = re.compile(r"\{\{\s*(.+?)\s*\}\}")
_VAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Subscript,
    ast.Slice,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


_FUNCTIONS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "clamp": _clamp,
    "coalesce": _coalesce,
    "if": lambda condition, truthy, falsy: truthy if condition else falsy,
    "_if": lambda condition, truthy, falsy: truthy if condition else falsy,
}


def evaluate(expression: str, variables: dict[str, Any]) -> Any:
    text = re.sub(r"\bif\s*\(", "_if(", expression.strip())
    tree = ast.parse(text, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Unsupported expression element: {type(node).__name__}")
    code = compile(tree, "<recipe>", "eval")
    scope = {**variables, **_FUNCTIONS}
    return eval(code, {"__builtins__": {}}, scope)  # noqa: S307 - AST is allowlisted


def resolve_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_value(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, variables) for item in value]
    if not isinstance(value, str):
        return value
    whole = _EXPR.fullmatch(value.strip())
    if whole:
        return evaluate(whole.group(1), variables)
    var_only = _VAR.fullmatch(value.strip())
    if var_only:
        return variables.get(var_only.group(1), value)
    resolved = _EXPR.sub(lambda match: str(evaluate(match.group(1), variables)), value)
    return _VAR.sub(lambda match: str(variables.get(match.group(1), match.group(0))), resolved)
