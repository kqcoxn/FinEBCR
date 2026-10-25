"""Run FinFUND on a selected dataset using an OpenAI-compatible endpoint."""

import argparse
import hashlib
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from finfund.data import ROOT, load


def read_config(path):
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("configuration must be a JSON object")
    allowed = {
        "dataset",
        "data_path",
        "corpus_path",
        "output_dir",
        "limit",
        "offset",
        "api",
        "runtime",
    }
    if set(config) - allowed:
        raise ValueError(
            "unknown configuration fields: " + ", ".join(sorted(set(config) - allowed))
        )
    if config.get("dataset") not in ("finqa", "tatqa", "university"):
        raise ValueError("invalid dataset")
    for name in ("limit", "offset"):
        value = config.get(name, 1 if name == "limit" else 0)
        if type(value) is not int or value < 0:
            raise ValueError(name + " must be a nonnegative integer")
    for name in ("data_path", "corpus_path", "output_dir"):
        if name in config and not isinstance(config[name], str):
            raise ValueError(name + " must be a path string")
        if config.get(name):
            config[name] = str((path.parent / config[name]).resolve())
    if not config.get("output_dir"):
        config["output_dir"] = str((path.parent / "outputs").resolve())
    api = config.get("api", {})
    if not isinstance(api, dict):
        raise ValueError("api must be an object")
    allowed_api = {
        "base_url",
        "model",
        "api_key_env",
        "temperature",
        "max_output_tokens",
        "max_input_tokens",
        "timeout_seconds",
        "extra_body",
    }
    if set(api) - allowed_api:
        raise ValueError("unknown API configuration fields")
    if not isinstance(api.get("model"), str) or not api["model"]:
        raise ValueError("model is required")
    if not isinstance(api.get("base_url"), str):
        raise ValueError("base_url must be a string")
    if not isinstance(api.get("api_key_env", ""), str):
        raise ValueError("api_key_env must be a string")
    for name, default in (("max_input_tokens", 16000), ("max_output_tokens", 1024)):
        value = api.get(name, default)
        if type(value) is not int or value <= 0:
            raise ValueError(name + " must be a positive integer")
    for name, default in (("temperature", 0), ("timeout_seconds", 120)):
        value = api.get(name, default)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(name + " must be a finite nonnegative number")
        if name == "timeout_seconds" and value == 0:
            raise ValueError("timeout_seconds must be positive")
    extra = api.get("extra_body", {})
    core_fields = {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "stream",
        "response_format",
    }
    if not isinstance(extra, dict) or set(extra) & core_fields:
        raise ValueError("extra_body must be an object without core request fields")
    from urllib.parse import urlparse

    url = urlparse(api.get("base_url", ""))
    if (
        url.scheme not in ("http", "https")
        or not url.netloc
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "base_url must be an HTTP(S) API base without credentials or query parameters"
        )
    runtime = config.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    allowed_runtime = {
        "tokenizer",
        "reranker",
        "device",
        "evidence_tokens",
        "candidate_count",
    }
    if set(runtime) - allowed_runtime:
        raise ValueError("unknown runtime configuration fields")
    if runtime.get("device", "auto") not in ("auto", "cpu", "cuda"):
        raise ValueError("device must be auto, cpu or cuda")
    for name in ("tokenizer", "reranker"):
        if not isinstance(runtime.get(name), str) or not runtime[name]:
            raise ValueError(name + " is required")
    for name, default in [("evidence_tokens", 3000), ("candidate_count", 40)]:
        value = runtime.get(name, default)
        if type(value) is not int or value <= 0:
            raise ValueError(name + " must be positive")
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).with_name("config.example.json")
    )
    parser.add_argument("--dataset", choices=["finqa", "tatqa", "university"])
    parser.add_argument(
        "--limit", type=int, help="number of questions; 0 means all remaining questions"
    )
    parser.add_argument("--offset", type=int, help="zero-based first question index")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate configuration and data; no model downloads or calls",
    )
    args = parser.parse_args(argv)
    config = read_config(args.config.resolve())
    for key in ("dataset", "limit", "offset"):
        value = getattr(args, key)
        if value is not None:
            config[key] = value
    limit, offset = config.get("limit", 1), config.get("offset", 0)
    if limit < 0 or offset < 0:
        raise ValueError("limit and offset must be nonnegative")
    items = load(config["dataset"], config.get("data_path"), config.get("corpus_path"))
    chosen = items[offset:] if limit == 0 else items[offset : offset + limit]
    if not chosen:
        raise ValueError("selected question range is empty")
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dataset": config["dataset"],
                    "available": len(items),
                    "selected": len(chosen),
                    "first_id": chosen[0]["id"],
                    "question": chosen[0]["question"],
                    "source_units": len(chosen[0]["sources"]),
                    "model": config["api"]["model"],
                    "calls": 0,
                },
                ensure_ascii=False,
            )
        )
        return 0
    env = config["api"].get("api_key_env", "")
    if env and not os.environ.get(env):
        raise ValueError("set environment variable " + env)
    from finfund.client import Client
    from finfund.pipeline import Pipeline
    from finfund.retrieval import Reranker, Tokenizer, chunks

    runtime = config["runtime"]
    codec = Tokenizer(runtime["tokenizer"])
    reranker = Reranker(runtime["reranker"], runtime.get("device", "auto"))
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    output = Path(config.get("output_dir", ROOT / "outputs")) / run_id
    output.mkdir(parents=True)
    source_hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "method").rglob("*.py")
    }
    (output / "run.json").write_text(
        json.dumps(
            {
                "configuration": config,
                "source_sha256": source_hashes,
                "selected_ids": [q["id"] for q in chosen],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    prepared = (
        chunks(chosen[0]["sources"], codec)
        if config["dataset"] == "university"
        else None
    )
    counts = {}
    for index, item in enumerate(chosen, offset):
        directory = output / f"{index:05d}"
        client = Client(config["api"], directory, codec)
        pipeline = Pipeline(
            client,
            codec,
            reranker,
            runtime.get("evidence_tokens", 3000),
            runtime.get("candidate_count", 40),
        )
        result = pipeline.answer(config["dataset"], item, prepared)
        result["request_count"] = len(client.calls)
        (directory / "answer.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(f"{index + 1}: {item['id']} {result['status']}", flush=True)
    (output / "summary.json").write_text(
        json.dumps({"questions": len(chosen), "statuses": counts}, indent=2),
        encoding="utf-8",
    )
    print("Output: " + str(output))
    return (
        1
        if any(s in counts for s in ("api_error", "invalid_format", "invalid_plan"))
        else 0
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        sys.exit(2)
