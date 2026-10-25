"""Bounded Decimal arithmetic with explicit source and dependency checks."""

import re
from decimal import Decimal, localcontext

from .data_numeric_tools import NUMBER, parse_literal
from .protocol import object_with

ARITY = {
    "lookup": (1, 1),
    "difference": (2, 2),
    "ratio": (2, 2),
    "percentage": (2, 2),
    "relative_change": (2, 2),
    "sum": (1, 6),
    "average": (1, 6),
    "multiply": (2, 2),
    "greater": (2, 2),
    "less": (2, 2),
    "equal": (2, 2),
}


def calculate(op, v):
    if op == "lookup":
        return v[0]
    if op == "difference":
        return v[0] - v[1]
    if op in ("ratio", "percentage"):
        return v[0] / v[1]
    if op == "relative_change":
        return (v[0] - v[1]) / v[1]
    if op == "sum":
        return sum(v, Decimal(0))
    if op == "average":
        return sum(v, Decimal(0)) / len(v)
    if op == "multiply":
        return v[0] * v[1]
    if op == "greater":
        return v[0] > v[1]
    if op == "less":
        return v[0] < v[1]
    if op == "equal":
        return v[0] == v[1]
    raise ValueError("unsupported operation")


def execute(raw, evidence, question):
    steps = object_with(raw, ["steps"])["steps"]
    if not isinstance(steps, list) or len(steps) > 4:
        raise ValueError("plan exceeds four steps")
    if not steps:
        return {"status": "abstain", "answer": "unknown", "trace": []}
    trace = []
    values = []
    sources = set()
    question_numbers = {m[0] for m in NUMBER.finditer(question)}
    with localcontext() as ctx:
        ctx.prec = 60
        for step in steps:
            if not isinstance(step, dict) or set(step) != {"operation", "operands"}:
                raise ValueError("invalid step fields")
            op, args = step["operation"], step["operands"]
            if not isinstance(op, str) or op not in ARITY or not isinstance(args, list):
                raise ValueError("invalid operation")
            lo, hi = ARITY[op]
            if not lo <= len(args) <= hi:
                raise ValueError("invalid operand count")
            operands = []
            origins = []
            for token in args:
                if not isinstance(token, str) or len(token) > 80:
                    raise ValueError("invalid operand")
                if re.fullmatch(r"#\d+", token):
                    index = int(token[1:])
                    if index >= len(values) or isinstance(values[index], bool):
                        raise ValueError("invalid backward reference")
                    value = values[index]
                    origin = {"step": index}
                elif token in ("C0", "C1"):
                    value = Decimal(token[1:])
                    origin = {"constant": token}
                else:
                    if token.startswith("Q:"):
                        if token[2:] not in question_numbers:
                            raise ValueError("number absent from question")
                        literal = token[2:]
                        origin = {"question": literal}
                    else:
                        if token not in evidence["numbers"]:
                            raise ValueError("number absent from evidence")
                        record = evidence["numbers"][token]
                        literal = record["raw"]
                        origin = {"id": token, **record}
                        sources.add(record["source"])
                    value, kind = parse_literal(literal)
                    if kind == "percent":
                        value /= 100
                operands.append(value)
                origins.append(origin)
            result = calculate(op, operands)
            if not isinstance(result, bool) and (
                not result.is_finite() or abs(result) >= Decimal("1e30")
            ):
                raise ValueError("invalid calculation result")
            values.append(result)
            trace.append({"operation": op, "inputs": origins, "result": str(result)})
    value = values[-1]
    answer = (
        ("yes" if value else "no") if isinstance(value, bool) else format(value, "f")
    )
    return {
        "status": "executed",
        "answer": answer,
        "trace": trace,
        "source_refs": sorted(sources),
    }
