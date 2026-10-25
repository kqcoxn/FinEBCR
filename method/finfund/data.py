"""Dataset adapters: inference receives questions and source material only."""

import json
from pathlib import Path

from . import data_finqa, data_tatqa

ROOT = Path(__file__).resolve().parents[2]


def load(dataset, data_path=None, corpus_path=None):
    if dataset not in ("finqa", "tatqa", "university"):
        raise ValueError("dataset must be finqa, tatqa or university")
    if dataset in ("finqa", "tatqa") and not data_path:
        raise ValueError(
            f"{dataset} requires data_path pointing to the downloaded upstream JSON file; see docs/data.md"
        )
    rows = json.loads(
        Path(data_path or ROOT / "university-dataset/qa.json").read_text(
            encoding="utf-8"
        )
    )
    if dataset == "university":
        corpus = json.loads(
            Path(corpus_path or ROOT / "university-dataset/corpus.json").read_text(
                encoding="utf-8"
            )
        )
        sources = [
            {
                "id": f"D{i}",
                "title": d["title"],
                "text": d["body"],
                "location": {"document": i},
            }
            for i, d in enumerate(corpus)
        ]
        return [
            {"id": f"university-{i:04d}", "question": q["query"], "sources": sources}
            for i, q in enumerate(rows)
        ]
    result = []
    for row in rows:
        questions = [row] if dataset == "finqa" else row["questions"]
        for q in questions:
            item = (
                data_finqa.public(q)
                if dataset == "finqa"
                else data_tatqa.public(row, q)
            )
            units = (
                data_finqa.units(item) if dataset == "finqa" else data_tatqa.units(item)
            )
            sources = [
                {
                    "id": u["id"],
                    "title": "",
                    "text": u["text"],
                    "location": {"unit": u["id"], "cells": u.get("cells", [])},
                }
                for u in units
            ]
            result.append(
                {"id": item["id"], "question": item["question"], "sources": sources}
            )
    return result
