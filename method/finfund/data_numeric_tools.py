"""Numeric literal matching and bounded Decimal conversion."""

from __future__ import annotations

import decimal
import re

NUMBER = re.compile(
    "(?<![\\w.,])(?:\\(\\s*[$€£]?\\s*(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?\\s*\\)|[+-]?(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?)(?:[ \\t]*%)?(?![\\w]|[.,]\\d)"
)
LITERAL = re.compile("[+-]?(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?\\Z")


class ToolError(ValueError):
    pass


def parse_literal(raw):
    if not isinstance(raw, str) or len(raw) > 64:
        raise ToolError("invalid_number")
    value = raw.strip()
    percent = value.endswith("%")
    if percent:
        value = value[:-1].strip()
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1].strip()
    value = value.lstrip("$€£").strip()
    if not LITERAL.fullmatch(value) or (negative and value.startswith(("+", "-"))):
        raise ToolError("invalid_number")
    number = decimal.Decimal(value.replace(",", "")) * (-1 if negative else 1)
    if abs(number) >= decimal.Decimal("1e20") or len(number.as_tuple().digits) > 20:
        raise ToolError("number_limit")
    return (number, "percent" if percent else "number_unknown_dimension")
