"""FinQA question and source-material adapters."""


def public(row):
    return {
        "id": row["id"],
        "question": row["qa"]["question"],
        "pre_text": row["pre_text"],
        "table": row["table"],
        "post_text": row["post_text"],
    }


def units(item):
    out = []

    def add(uid, text, cells=None):
        out.append({"id": uid, "text": text, "order": len(out), "cells": cells or []})

    for i, text in enumerate(item["pre_text"]):
        add(f"text_{i}", text)
    header = item["table"][0]
    for i, row in enumerate(item["table"]):
        if len(row) != len(header):
            raise ValueError("ragged table")
        if i == 0:
            text = " | ".join(row)
        else:
            prefix = header[0] + " | " if header[0] else ""
            text = (
                prefix
                + row[0]
                + "; "
                + "; ".join((f"{h}: {v}" for h, v in zip(header[1:], row[1:])))
            )
        add(
            f"table_{i}",
            text,
            [[i, j] for j in range(len(row))]
            + ([[0, j] for j in range(len(header))] if i else []),
        )
    for i, text in enumerate(item["post_text"], len(item["pre_text"])):
        add(f"text_{i}", text)
    return out
