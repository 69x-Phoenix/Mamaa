"""Safe calculator. Uses the ast module - never eval()."""
from __future__ import annotations

import ast
import math
import operator as op
from typing import Any

from tools.registry import Permission, ToolError, ToolSpec

_BIN = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv, ast.Mod: op.mod, ast.Pow: op.pow,
}
_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg}
_FUNCS = {
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "abs": abs, "round": round,
    "floor": math.floor, "ceil": math.ceil, "min": min, "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}
_MAX_LEN = 200


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and right > 0 and abs(left) not in (0, 1):
            if right * math.log10(abs(left)) > 10_000:
                raise ToolError("Exponent too large")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ToolError("Unsupported expression. Use numbers, + - * / // % **, parentheses, and sqrt/log/sin/etc.")


def calculate(expression: str) -> dict[str, Any]:
    """Evaluate an arithmetic expression safely."""
    if len(expression) > _MAX_LEN:
        raise ToolError(f"Expression longer than {_MAX_LEN} characters")
    try:
        value = _eval(ast.parse(expression.strip(), mode="eval"))
    except SyntaxError as exc:
        raise ToolError(f"Invalid syntax (use ** for powers, not ^): {exc.msg}") from exc
    except (ZeroDivisionError, ValueError, OverflowError, TypeError) as exc:
        raise ToolError(f"Math error: {exc}") from exc
    return {"expression": expression, "result": value}


CALCULATOR = ToolSpec(
    name="calculator",
    description="Evaluate an arithmetic expression exactly (e.g. '(1250*12)/100'). Use this for ANY calculation instead of doing math in your head.",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "Arithmetic expression, e.g. '2*(3+4)**2'"}},
        "required": ["expression"],
    },
    func=calculate,
    permission=Permission.READ_ONLY,
    timeout=5,
)
