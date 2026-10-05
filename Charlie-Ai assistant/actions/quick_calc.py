# actions/quick_calc.py
"""
Quick Math, Currency & Unit Converter for Charlie.

Voice commands:
  "What is 15% of 850?"
  "Convert 100 USD to INR"
  "Convert 72 Fahrenheit to Celsius"
  "What is 5 miles in kilometers?"
  "Calculate 250 * 18"
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any, Dict, Optional, Union

TOOL = {
    "name": "quick_calc",
    "description": (
        "Performs instant arithmetic calculations, percentage calculations, "
        "unit conversions (length, weight, temperature, data), and currency conversions. "
        "Trigger on: 'calculate', 'what is', 'convert', 'how much is', 'percentage of', 'plus', 'minus', 'divided by'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Calculation or conversion query (e.g., '15% of 850', '100 USD to INR', '5 miles to km')",
            },
        },
        "required": ["query"],
    },
}

# Safe AST Math Evaluator (NO raw eval)
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> Union[int, float]:
    def _eval_node(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Invalid number")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type in _OPERATORS:
                return _OPERATORS[op_type](_eval_node(node.left), _eval_node(node.right))
            raise ValueError(f"Unsupported operator: {op_type}")
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in _OPERATORS:
                return _OPERATORS[op_type](_eval_node(node.operand))
            raise ValueError("Unsupported unary operator")
        raise ValueError("Invalid expression syntax")

    parsed = ast.parse(expr, mode="eval")
    return _eval_node(parsed.body)


# Baseline FX Rates (per 1 USD)
_FX_RATES = {
    "USD": 1.0,
    "INR": 86.8,
    "EUR": 0.95,
    "GBP": 0.79,
    "AED": 3.67,
    "CAD": 1.42,
    "AUD": 1.58,
    "JPY": 154.5,
    "SGD": 1.35,
}

_UNIT_CONVERSIONS = {
    # Length to meters
    "meter": 1.0, "meters": 1.0, "m": 1.0,
    "kilometer": 1000.0, "kilometers": 1000.0, "km": 1000.0,
    "mile": 1609.34, "miles": 1609.34,
    "foot": 0.3048, "feet": 0.3048, "ft": 0.3048,
    "inch": 0.0254, "inches": 0.0254, "in": 0.0254,
    "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
    # Weight to kg
    "kg": 1.0, "kilogram": 1.0, "kilograms": 1.0,
    "gram": 0.001, "grams": 0.001, "g": 0.001,
    "pound": 0.453592, "pounds": 0.453592, "lbs": 0.453592, "lb": 0.453592,
    "ounce": 0.0283495, "ounces": 0.0283495, "oz": 0.0283495,
    # Data to MB
    "mb": 1.0, "gb": 1024.0, "tb": 1048576.0, "kb": 0.0009765625,
}


def execute(query: str, **kwargs: Any) -> str:
    """Execute quick calculation or conversion."""
    q = query.strip()

    # 1. Percentage check: "15% of 850" or "what is 20 percent of 500"
    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(\d+(?:\.\d+)?)", q, re.I)
    if pct_match:
        pct = float(pct_match.group(1))
        val = float(pct_match.group(2))
        res = (pct / 100.0) * val
        return f"📊 {pct}% of {val} is **{res:g}**"

    # 2. Currency conversion: "100 USD to INR" or "convert 50 eur to usd"
    fx_match = re.search(
        r"(\d+(?:\.\d+)?)\s*([a-zA-Z]{3})\s+(?:to|in)\s+([a-zA-Z]{3})", q, re.I
    )
    if fx_match:
        amount = float(fx_match.group(1))
        src_curr = fx_match.group(2).upper()
        tgt_curr = fx_match.group(3).upper()

        if src_curr in _FX_RATES and tgt_curr in _FX_RATES:
            val_in_usd = amount / _FX_RATES[src_curr]
            converted = val_in_usd * _FX_RATES[tgt_curr]
            return f"💱 {amount:g} {src_curr} ≈ **{converted:,.2f} {tgt_curr}**"

    # 3. Temperature: "75 f to c" or "30 c to f"
    temp_match = re.search(r"(-?\d+(?:\.\d+)?)\s*([cf])\s+(?:to|in)\s+([cf])", q, re.I)
    if temp_match:
        t_val = float(temp_match.group(1))
        src_t = temp_match.group(2).lower()
        tgt_t = temp_match.group(3).lower()
        if src_t == "f" and tgt_t == "c":
            c_val = (t_val - 32) * 5 / 9
            return f"🌡️ {t_val:g}°F = **{c_val:.1f}°C**"
        elif src_t == "c" and tgt_t == "f":
            f_val = (t_val * 9 / 5) + 32
            return f"🌡️ {t_val:g}°C = **{f_val:.1f}°F**"

    # 4. Physical unit conversion: "5 miles to km" or "10 kg to lbs"
    unit_match = re.search(
        r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s+(?:to|in)\s+([a-zA-Z]+)", q, re.I
    )
    if unit_match:
        val = float(unit_match.group(1))
        src_u = unit_match.group(2).lower()
        tgt_u = unit_match.group(3).lower()

        if src_u in _UNIT_CONVERSIONS and tgt_u in _UNIT_CONVERSIONS:
            std_val = val * _UNIT_CONVERSIONS[src_u]
            final_val = std_val / _UNIT_CONVERSIONS[tgt_u]
            return f"📏 {val:g} {src_u} = **{final_val:.2f} {tgt_u}**"

    # 5. Direct arithmetic expression: "250 * 18 + 45" or "144 / 12"
    clean_expr = re.sub(r"[^\d+\-*/().%^eE ]", "", q.replace("x", "*").replace("X", "*"))
    clean_expr = clean_expr.strip()
    if clean_expr and any(c.isdigit() for c in clean_expr):
        try:
            val = _safe_eval(clean_expr)
            return f"🔢 {clean_expr} = **{val:g}**"
        except Exception:
            pass

    return f"Could not calculate '{query}'. Try: '15% of 850', '100 USD to INR', or '5 miles to km'."
