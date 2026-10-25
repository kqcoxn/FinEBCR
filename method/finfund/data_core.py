"""Strict JSON parsing with duplicate-key and non-finite-value checks."""

from __future__ import annotations

import json


def strict_json(text: str):

    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError(f"duplicate JSON key: {k}")
            out[k] = v
        return out

    def invalid(value):
        raise ValueError(f"non-finite JSON: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
