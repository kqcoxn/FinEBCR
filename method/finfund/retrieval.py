"""Question/need retrieval, semantic reranking and bounded source packing."""

import json
import math
import re
from collections import Counter

from .data_numeric_tools import NUMBER, parse_literal


def terms(text):
    return re.findall(r"[\u3400-\u9fff]|[a-z]+|\d+(?:\.\d+)?", text.lower())


def bm25(query, sources):
    counts = [Counter(terms(s["title"] + " " + s["text"])) for s in sources]
    df = Counter(t for c in counts for t in c)
    avg = sum(map(lambda c: sum(c.values()), counts)) / max(1, len(counts))
    return [
        sum(
            math.log(1 + (len(counts) - df[t] + 0.5) / (df[t] + 0.5))
            * c[t]
            * 2.2
            / (c[t] + 1.2 * (0.25 + 0.75 * sum(c.values()) / max(1, avg)))
            for t in set(terms(query))
            if c[t]
        )
        for c in counts
    ]


def chunks(sources, codec, cap=220):
    result = []
    for source in sources:
        text = source["text"]
        # Each table row retains its header/value associations as one candidate.
        if source["location"].get("cells"):
            ranges = [(0, len(text))]
        else:
            ranges = []
            for m in re.finditer(r"[^\r\n]+", text):
                start = m.start()
                while start < m.end():
                    offsets = codec.offsets(text[start : m.end()])
                    end = m.end() if len(offsets) <= cap else start + offsets[cap][0]
                    if end <= start:
                        raise ValueError(
                            "tokenizer cannot produce character-safe chunks"
                        )
                    ranges.append((start, end))
                    start = end
        for start, end in ranges:
            if text[start:end].strip():
                result.append(
                    {
                        **source,
                        "id": f"S{len(result)}",
                        "origin": source["id"],
                        "start": start,
                        "end": end,
                        "text": text[start:end],
                    }
                )
    return result


def organize(question, needs, sources, codec, reranker, budget, candidate_count):
    queries = [question] + needs["slots"] + needs["conditions"]
    scores = [0.0] * len(sources)
    for query in queries:
        values = bm25(query, sources)
        for rank, i in enumerate(
            sorted(range(len(sources)), key=lambda i: (-values[i], i))
        ):
            scores[i] += 1 / (61 + rank)
    ids = sorted(range(len(sources)), key=lambda i: (-scores[i], i))[:candidate_count]
    candidates = [sources[i] for i in ids]
    semantic = reranker.score(
        question, [s["title"] + "\n" + s["text"] for s in candidates]
    )
    if len(semantic) != len(candidates) or not all(math.isfinite(x) for x in semantic):
        raise ValueError("invalid reranker scores")
    selected = []
    for i in sorted(range(len(candidates)), key=lambda i: (-semantic[i], i)):
        trial = selected + [candidates[i]]
        if codec.count(json.dumps(trial, ensure_ascii=False)) <= budget:
            selected = trial
    # Return sources in their original sequence after relevance-based selection.
    selected.sort(key=lambda s: int(s["id"][1:]))
    numbers = {}
    for source in selected:
        for match in NUMBER.finditer(source["text"]):
            try:
                parse_literal(match[0])
            except ValueError:
                continue
            numbers[f"N{len(numbers)}"] = {
                "raw": match[0],
                "source": source["id"],
                "start": source["start"] + match.start(),
                "end": source["start"] + match.end(),
            }
    return {
        "sources": selected,
        "numbers": numbers,
        "tokens": codec.count(json.dumps(selected, ensure_ascii=False)),
    }


class Tokenizer:
    def __init__(self, name):
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(
            name, use_fast=True, trust_remote_code=False
        )
        if not self.tokenizer.is_fast:
            raise ValueError("a fast tokenizer with offsets is required")

    def offsets(self, text):
        return self.tokenizer(
            text, add_special_tokens=False, return_offsets_mapping=True
        )["offset_mapping"]

    def count(self, text):
        return len(self.tokenizer.encode(text, add_special_tokens=False))


class Reranker:
    def __init__(self, name, device="auto"):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.device = (
            ("cuda" if torch.cuda.is_available() else "cpu")
            if device == "auto"
            else device
        )
        self.tokenizer = AutoTokenizer.from_pretrained(name, trust_remote_code=False)
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(
                name, trust_remote_code=False
            )
            .to(self.device)
            .eval()
        )
        self.limit = min(
            8192,
            int(self.tokenizer.model_max_length),
            int(getattr(self.model.config, "max_position_embeddings", 8194)) - 2,
        )

    def score(self, query, texts):
        result = []
        for start in range(0, len(texts), 4):
            pairs = [[query, text] for text in texts[start : start + 4]]
            inputs = self.tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=self.limit,
                return_tensors="pt",
            ).to(self.device)
            with self.torch.inference_mode():
                result.extend(
                    self.model(**inputs).logits.view(-1).float().cpu().tolist()
                )
        return result
