"""Original policy units, adjacency closure and constrained rewriting."""

import json
import re

from .protocol import object_with, strings


def units(evidence, question, codec, budget):
    raw = []
    for source in evidence["sources"]:
        local = []
        text = source["text"]
        bounds = [0] + [m.end() for m in re.finditer("[。；！？]", text)]
        if bounds[-1] != len(text):
            bounds.append(len(text))
        for start, end in zip(bounds, bounds[1:]):
            if text[start:end].strip():
                unit = {
                    "id": f"U{len(raw)}",
                    "ref": source["id"],
                    "title": source["title"],
                    "start": source["start"] + start,
                    "end": source["start"] + end,
                    "text": text[start:end],
                    "dependencies": [],
                }
                raw.append(unit)
                local.append(unit)
        for i, u in enumerate(local):
            if i and re.match(r"\s*(但|其中|除外|除非|否则|上述|该项)", u["text"]):
                u["dependencies"].append(local[i - 1]["id"])
            if i + 1 < len(local) and re.match(
                r"\s*(但|除外|除非|否则)", local[i + 1]["text"]
            ):
                u["dependencies"].append(local[i + 1]["id"])
    from .retrieval import terms

    query = set(terms(question))
    index = {u["id"]: u for u in raw}
    kept = {}
    for unit in sorted(
        raw, key=lambda u: (-len(query & set(terms(u["text"]))), int(u["id"][1:]))
    ):
        group = closure([unit["id"]], index)
        trial = {**kept, **{k: index[k] for k in group}}
        if (
            len(trial) <= 48
            and codec.count(json.dumps(list(trial.values()), ensure_ascii=False))
            <= budget
        ):
            kept = trial
    return [u for u in raw if u["id"] in kept]


def closure(ids, index):
    chosen = set()
    stack = list(ids)
    while stack:
        key = stack.pop()
        if key not in index:
            raise ValueError("unknown policy unit")
        if key not in chosen:
            chosen.add(key)
            stack.extend(index[key]["dependencies"])
    return chosen


def select(raw, available):
    value = object_with(raw, ["answer_ids", "condition_ids"])
    ids = strings(value["answer_ids"], 8) + strings(value["condition_ids"], 8)
    chosen = closure(ids, {u["id"]: u for u in available})
    return [u for u in available if u["id"] in chosen]
