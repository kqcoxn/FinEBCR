import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

METHOD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(METHOD))
from finfund import policy, protocol
from finfund.client import Client
from finfund.data import load
from finfund.executor import execute
from finfund.pipeline import Pipeline
from finfund.retrieval import chunks, organize


class Codec:
    def count(self, text):
        return len(text)

    def offsets(self, text):
        return [(i, i + 1) for i in range(len(text))]


class Ranker:
    def score(self, query, texts):
        return [float(len(texts) - i) for i in range(len(texts))]


def fixture(dataset, directory):
    """Create synthetic adapter inputs; no benchmark records are bundled."""
    if dataset == "finqa":
        rows = [
            {
                "id": "synthetic-finqa",
                "pre_text": ["Revenue is 100."],
                "table": [["year", "revenue"], ["2025", "100"]],
                "post_text": [],
                "qa": {
                    "question": "What is revenue?",
                    "exe_ans": "GOLD_SECRET",
                    "gold_inds": {"text_0": "GOLD_SECRET"},
                    "program": "GOLD_SECRET",
                },
            }
        ]
    else:
        rows = [
            {
                "table": {
                    "uid": "synthetic-table",
                    "table": [["year", "revenue"], ["2025", "100"]],
                },
                "paragraphs": [{"order": 1, "text": "Revenue is 100."}],
                "questions": [
                    {
                        "uid": "synthetic-tatqa",
                        "question": "What is revenue?",
                        "answer": "GOLD_SECRET",
                        "answer_type": "span",
                        "scale": "",
                        "derivation": "GOLD_SECRET",
                    }
                ],
            }
        ]
    path = Path(directory) / (dataset + ".json")
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def response(value):
    return io.BytesIO(
        json.dumps(
            {
                "choices": [
                    {
                        "message": {"content": json.dumps(value, ensure_ascii=False)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        ).encode()
    )


class FrameworkTests(unittest.TestCase):
    def test_external_datasets_and_gold_isolation(self):
        rows = load("university")
        self.assertEqual(len(rows), 349)
        for r in rows:
            self.assertEqual(set(r), {"id", "question", "sources"})
        self.assertEqual(len(load("university")[0]["sources"]), 86)
        with tempfile.TemporaryDirectory() as d:
            for ds in ("finqa", "tatqa"):
                with self.assertRaisesRegex(ValueError, "requires data_path"):
                    load(ds)
                rows = load(ds, fixture(ds, d))
                self.assertEqual(len(rows), 1)
                self.assertEqual(set(rows[0]), {"id", "question", "sources"})
                self.assertNotIn("GOLD_SECRET", json.dumps(rows))

    def test_source_slices_and_budget(self):
        sources = [
            {
                "id": "D0",
                "title": "rules",
                "text": "A" * 500,
                "location": {"document": 0},
            }
        ]
        split = chunks(sources, Codec())
        self.assertEqual("".join(x["text"] for x in split), "A" * 500)
        packed = organize(
            "A", {"slots": [], "conditions": []}, split, Codec(), Ranker(), 500, 40
        )
        self.assertLessEqual(packed["tokens"], 500)
        for s in packed["sources"]:
            self.assertEqual(s["text"], sources[0]["text"][s["start"] : s["end"]])

    def test_arithmetic_and_validation(self):
        evidence = {
            "numbers": {
                "N0": {"raw": "120", "source": "S0"},
                "N1": {"raw": "100", "source": "S1"},
                "N2": {"raw": "20%", "source": "S0"},
            }
        }
        plan = {
            "steps": [
                {"operation": "relative_change", "operands": ["N0", "N1"]},
                {"operation": "multiply", "operands": ["#0", "N1"]},
            ]
        }
        result = execute(json.dumps(plan), evidence, "What is the change?")
        self.assertEqual(result["answer"], "20.0")
        self.assertEqual(len(result["trace"]), 2)
        self.assertEqual(
            execute(
                json.dumps({"steps": [{"operation": "lookup", "operands": ["N2"]}]}),
                evidence,
                "",
            )["answer"],
            "0.2",
        )
        for operands in [["N99"], ["#0"], ["Q:999"]]:
            with self.assertRaises(ValueError):
                execute(
                    json.dumps(
                        {"steps": [{"operation": "lookup", "operands": operands}]}
                    ),
                    evidence,
                    "",
                )
        with self.assertRaises(ArithmeticError):
            execute(
                json.dumps(
                    {"steps": [{"operation": "ratio", "operands": ["N0", "C0"]}]}
                ),
                evidence,
                "",
            )
        with self.assertRaises(ValueError):
            execute('{"steps":[],"steps":[]}', evidence, "")
        with self.assertRaises(ValueError):
            execute(
                json.dumps(
                    {"steps": [{"operation": "lookup", "operands": ["N0"]}] * 5}
                ),
                evidence,
                "",
            )

    def test_binding_reference_check(self):
        with self.assertRaises(ValueError):
            protocol.bindings(
                json.dumps(
                    {"bindings": [{"role_id": "R0", "refs": ["S99"], "note": ""}]}
                ),
                {"R0": "revenue"},
                {"sources": [{"id": "S0"}], "numbers": {}},
            )

    def test_policy_condition_closure(self):
        evidence = {
            "sources": [
                {
                    "id": "S0",
                    "title": "规定",
                    "text": "可以报销。但须审批。",
                    "start": 0,
                }
            ]
        }
        units = policy.units(evidence, "报销", Codec(), 10000)
        selected = policy.select('{"answer_ids":["U0"],"condition_ids":[]}', units)
        self.assertEqual(len(selected), 2)
        with self.assertRaises(ValueError):
            policy.select('{"answer_ids":["U99"],"condition_ids":[]}', units)

    def test_all_pipelines_through_http_transport(self):
        item = {
            "id": "sample",
            "question": "What is revenue?",
            "sources": [
                {
                    "id": "D0",
                    "title": "report",
                    "text": "Revenue is 100.",
                    "location": {},
                }
            ],
        }
        for ds, answers, expected in [
            (
                "finqa",
                [{"steps": [{"operation": "lookup", "operands": ["N0"]}]}],
                "100",
            ),
            ("tatqa", [{"answer": "100", "scale": "million"}], "100"),
            (
                "university",
                [
                    {"answer_ids": ["U0"], "condition_ids": []},
                    {"answer": "依据所给材料，收入为100。"},
                ],
                "依据所给材料，收入为100。",
            ),
        ]:
            replies = [
                {"slots": ["revenue"], "conditions": []},
                {"bindings": [{"role_id": "R0", "refs": ["N0"], "note": ""}]},
            ] + answers
            with tempfile.TemporaryDirectory() as d:
                cfg = {
                    "model": "mock",
                    "base_url": "http://localhost:1234/v1",
                    "api_key_env": "",
                    "max_input_tokens": 20000,
                }
                with patch(
                    "finfund.client.urlopen", side_effect=[response(r) for r in replies]
                ) as http:
                    client = Client(cfg, d, Codec())
                    result = Pipeline(client, Codec(), Ranker(), 10000).answer(ds, item)
                self.assertEqual(result["answer"], expected)
                self.assertEqual(
                    result["status"], "executed" if ds == "finqa" else "answered"
                )
                self.assertEqual(http.call_count, len(replies))
                self.assertEqual(len(list(Path(d).glob("*.json"))), len(replies))
                bodies = [json.loads(call.args[0].data) for call in http.call_args_list]
                self.assertTrue(
                    all(b["model"] == "mock" and not b["stream"] for b in bodies)
                )
                if ds == "university":
                    selected_payload = json.loads(bodies[2]["messages"][1]["content"])
                    self.assertEqual(selected_payload["roles"]["R0"], "revenue")
                    self.assertEqual(selected_payload["numbers"]["N0"]["raw"], "100")
                    self.assertEqual(
                        selected_payload["numbers"]["N0"]["source"],
                        selected_payload["units"][0]["ref"],
                    )

    def test_invalid_binding_stops_before_solver(self):
        with tempfile.TemporaryDirectory() as d:
            replies = [
                {"slots": ["value"], "conditions": []},
                {"bindings": [{"role_id": "R0", "refs": ["S99"], "note": ""}]},
            ]
            with patch(
                "finfund.client.urlopen", side_effect=[response(r) for r in replies]
            ) as http:
                client = Client(
                    {
                        "model": "mock",
                        "base_url": "http://localhost/v1",
                        "api_key_env": "",
                    },
                    d,
                )
                result = Pipeline(client, Codec(), Ranker(), 10000).answer(
                    "finqa",
                    {
                        "id": "x",
                        "question": "value?",
                        "sources": [
                            {
                                "id": "D",
                                "text": "value 100",
                                "title": "",
                                "location": {},
                            }
                        ],
                    },
                )
            self.assertEqual(result["status"], "invalid_format")
            self.assertEqual(http.call_count, 2)

    def test_truncated_response_and_receipt(self):
        data = {
            "choices": [
                {"message": {"content": '{"steps":'}, "finish_reason": "length"}
            ]
        }
        with tempfile.TemporaryDirectory() as d:
            with patch(
                "finfund.client.urlopen",
                return_value=io.BytesIO(json.dumps(data).encode()),
            ):
                client = Client(
                    {
                        "model": "mock",
                        "base_url": "http://localhost/v1",
                        "api_key_env": "",
                    },
                    d,
                )
                with self.assertRaises(RuntimeError):
                    client.complete("solve", "instruction", {})
            self.assertEqual(
                json.loads(next(Path(d).glob("*.json")).read_text())["status"],
                "invalid_response",
            )

    def test_cli_runs_and_preserves_outputs_without_real_models(self):
        spec = importlib.util.spec_from_file_location("finfund_run", METHOD / "run.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as d:
            config = json.loads((METHOD / "config.example.json").read_text())
            config["api"].update(
                model="mock",
                base_url="http://localhost/v1",
                api_key_env="",
                max_input_tokens=50000,
            )
            config["runtime"]["evidence_tokens"] = 10000
            config["output_dir"] = "results"
            path = Path(d) / "config.json"
            path.write_text(json.dumps(config))
            for dataset in ["finqa", "tatqa", "university"]:
                config["data_path"] = (
                    fixture(dataset, d).name if dataset != "university" else ""
                )
                path.write_text(json.dumps(config))
                if dataset != "university":
                    self.assertEqual(
                        cli.read_config(path)["data_path"],
                        str((Path(d) / config["data_path"]).resolve()),
                    )

                def reply(request, **kwargs):
                    body = json.loads(request.data)
                    instruction = body["messages"][0]["content"]
                    payload = json.loads(body["messages"][1]["content"])
                    if instruction == protocol.NEEDS:
                        return response({"slots": ["facts"], "conditions": []})
                    if instruction == protocol.BIND:
                        return response(
                            {
                                "bindings": [
                                    {
                                        "role_id": "R0",
                                        "refs": [payload["sources"][0]["id"]],
                                        "note": "",
                                    }
                                ]
                            }
                        )
                    if instruction == protocol.NUMERIC:
                        return response(
                            {
                                "steps": [
                                    {
                                        "operation": "lookup",
                                        "operands": [next(iter(payload["numbers"]))],
                                    }
                                ]
                            }
                        )
                    if instruction == protocol.TABLE:
                        return response({"answer": "test answer", "scale": ""})
                    if instruction == protocol.SELECT:
                        return response(
                            {
                                "answer_ids": [payload["units"][0]["id"]],
                                "condition_ids": [],
                            }
                        )
                    return response({"answer": "依据原文形成的测试回答。"})

                with (
                    patch("finfund.retrieval.Tokenizer", return_value=Codec()),
                    patch("finfund.retrieval.Reranker", return_value=Ranker()),
                    patch("finfund.client.urlopen", side_effect=reply),
                ):
                    self.assertEqual(
                        cli.main(
                            [
                                "--config",
                                str(path),
                                "--dataset",
                                dataset,
                                "--limit",
                                "1",
                            ]
                        ),
                        0,
                    )
            runs = list((Path(d) / "results").iterdir())
            self.assertEqual(len(runs), 3)
            for folder in runs:
                self.assertTrue((folder / "run.json").is_file())
                self.assertTrue((folder / "summary.json").is_file())
                self.assertTrue((folder / "00000/answer.json").is_file())
            bad = dict(config, enable_binding=False)
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                cli.read_config(path)

    def test_malformed_api_objects_are_recorded(self):
        for value in ([], None, 123, {"choices": [None]}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as d:
                with patch(
                    "finfund.client.urlopen",
                    return_value=io.BytesIO(json.dumps(value).encode()),
                ):
                    client = Client(
                        {
                            "model": "mock",
                            "base_url": "http://localhost/v1",
                            "api_key_env": "",
                        },
                        d,
                    )
                    with self.assertRaisesRegex(RuntimeError, "Invalid API response"):
                        client.complete("needs", protocol.NEEDS, {"question": "test"})
                receipt = json.loads(next(Path(d).glob("*.json")).read_text())
                self.assertEqual(receipt["status"], "invalid_response")
                self.assertIsNone(receipt["usage"])

    def test_config_validation_and_output_path(self):
        spec = importlib.util.spec_from_file_location("finfund_run", METHOD / "run.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        base = json.loads((METHOD / "config.example.json").read_text())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            for field, value in [
                ("api", []),
                ("runtime", []),
                ("data_path", 2),
                ("api", dict(base["api"], timeout_seconds=0)),
                ("api", dict(base["api"], max_input_tokens="1000")),
                ("api", dict(base["api"], extra_body={"messages": []})),
                ("runtime", dict(base["runtime"], device="typo")),
            ]:
                with self.subTest(field=field, value=value):
                    path.write_text(json.dumps(dict(base, **{field: value})))
                    with self.assertRaises(ValueError):
                        cli.read_config(path)
            for value in (None, ""):
                config = dict(base)
                config.pop("output_dir")
                if value is not None:
                    config["output_dir"] = value
                path.write_text(json.dumps(config))
                self.assertEqual(
                    cli.read_config(path)["output_dir"], str(Path(d) / "outputs")
                )

    def test_request_limit_stops_before_api_call(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("finfund.client.urlopen") as http:
                client = Client(
                    {
                        "model": "mock",
                        "base_url": "http://localhost/v1",
                        "api_key_env": "",
                        "max_input_tokens": 1,
                    },
                    d,
                    Codec(),
                )
                with self.assertRaisesRegex(ValueError, "exceeds max_input_tokens"):
                    client.complete("needs", protocol.NEEDS, {"question": "test"})
            http.assert_not_called()
            self.assertEqual(list(Path(d).glob("*.json")), [])

    def test_authentication_is_not_saved_in_receipts(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"TEST_KEY": "private-test-value"}),
        ):
            with patch(
                "finfund.client.urlopen",
                return_value=response({"slots": [], "conditions": []}),
            ):
                client = Client(
                    {
                        "model": "mock",
                        "base_url": "http://localhost/v1",
                        "api_key_env": "TEST_KEY",
                    },
                    d,
                )
                client.complete("needs", protocol.NEEDS, {"question": "test"})
            text = next(Path(d).glob("*.json")).read_text()
            self.assertNotIn("private-test-value", text)
            self.assertNotIn("Authorization", text)


if __name__ == "__main__":
    unittest.main()
