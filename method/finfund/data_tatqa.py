"""TAT-QA source adapters and answer/scale validation."""

from __future__ import annotations

from . import data_core, data_finqa

SCALES = ["", "thousand", "million", "billion", "percent"]


def public(ctx, question):
    return {
        "id": question["uid"],
        "context_id": ctx["table"]["uid"],
        "question": question["question"],
        "table": ctx["table"]["table"],
        "paragraphs": [
            {"order": p["order"], "text": p["text"]}
            for p in sorted(ctx["paragraphs"], key=lambda p: p["order"])
        ],
    }


def units(item):
    result = data_finqa.units({"pre_text": [], "table": item["table"], "post_text": []})
    for p in item["paragraphs"]:
        result.append(
            {
                "id": f"paragraph_{p['order']}",
                "text": p["text"],
                "order": len(result),
                "cells": [],
            }
        )
    return result


def parse(raw):
    try:
        obj = data_core.strict_json(raw)
        if not isinstance(obj, dict) or set(obj) != {"answer", "scale"}:
            raise ValueError("expected answer and scale")
        answer, scale = (obj["answer"], obj["scale"])
        if not isinstance(scale, str) or scale not in SCALES:
            raise ValueError("invalid scale")
        if isinstance(answer, str):
            if not answer.strip():
                raise ValueError("empty answer")
            if answer.strip().lower() == "unknown":
                return ("abstain", None, scale)
        elif (
            not isinstance(answer, list)
            or not answer
            or (not all((isinstance(a, str) and a.strip() for a in answer)))
        ):
            raise ValueError("answer must be string or nonempty string list")
        return ("ok", answer, scale)
    except (ValueError, TypeError):
        return ("invalid_format", None, None)
