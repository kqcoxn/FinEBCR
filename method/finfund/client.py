"""OpenAI-compatible JSON transport and per-request receipts."""

import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import protocol


class Client:
    def __init__(self, config, directory, codec=None):
        self.config = config
        self.directory = Path(directory)
        self.codec = codec
        self.calls = []
        self.key = os.environ.get(config.get("api_key_env", ""), "")
        if config.get("api_key_env") and not self.key:
            raise ValueError(
                "missing API key environment variable: " + config["api_key_env"]
            )
        self.directory.mkdir(parents=True, exist_ok=True)

    def complete(self, stage, instruction, payload):
        messages = protocol.messages(instruction, payload)
        if self.codec and self.codec.count(
            json.dumps(messages, ensure_ascii=False)
        ) > self.config.get("max_input_tokens", 16000):
            raise ValueError("request exceeds max_input_tokens at " + stage)
        body = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": self.config.get("temperature", 0),
            "max_tokens": self.config.get("max_output_tokens", 1024),
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        extra = self.config.get("extra_body", {})
        if not isinstance(extra, dict) or set(extra) & set(body):
            raise ValueError("extra_body cannot replace core request fields")
        body.update(extra)
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        request = Request(
            self.config["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        receipt = {"stage": stage, "request": body, "status": "started", "usage": None}
        start = time.monotonic()
        try:
            with urlopen(
                request, timeout=self.config.get("timeout_seconds", 120)
            ) as response:
                obj = json.loads(response.read().decode("utf-8"))
            receipt["response"] = obj
            if not isinstance(obj, dict):
                raise ValueError("expected an API response object")
            receipt["usage"] = obj.get("usage")
            choice = obj["choices"][0]
            if not isinstance(choice, dict):
                raise ValueError("expected a response choice object")
            content = choice["message"]["content"]
            if choice.get("finish_reason") not in (None, "stop"):
                raise ValueError("response did not finish normally")
            if not isinstance(content, str):
                raise ValueError("missing text response")
            receipt["status"] = "completed"
            return content
        except HTTPError as exc:
            receipt.update(status="api_error", error=f"HTTP {exc.code}")
            raise RuntimeError(f"HTTP {exc.code} at {stage}") from None
        except (URLError, TimeoutError, OSError):
            receipt.update(status="api_error", error="connection or timeout error")
            raise RuntimeError("API connection failed at " + stage) from None
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            receipt.update(status="invalid_response", error=str(exc))
            raise RuntimeError("Invalid API response at " + stage) from None
        finally:
            receipt["seconds"] = time.monotonic() - start
            self.calls.append(receipt)
            path = self.directory / f"{len(self.calls):02d}-{stage}.json"
            path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
            )
