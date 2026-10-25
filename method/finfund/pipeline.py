"""One shared evidence/binding pipeline, followed by task-specific answer handling."""

from . import policy, protocol
from .data_tatqa import parse as parse_table
from .executor import execute
from .retrieval import chunks, organize


class Pipeline:
    def __init__(
        self, client, codec, reranker, evidence_tokens=3000, candidate_count=40
    ):
        self.client = client
        self.codec = codec
        self.reranker = reranker
        self.budget = evidence_tokens
        self.candidates = candidate_count

    def answer(self, dataset, item, prepared_sources=None):
        out = {
            "id": item["id"],
            "dataset": dataset,
            "question": item["question"],
            "status": "started",
        }
        try:
            raw = self.client.complete(
                "needs", protocol.NEEDS, {"question": item["question"]}
            )
            needs = protocol.needs(raw)
            out["needs"] = needs
            sources = (
                prepared_sources
                if prepared_sources is not None
                else chunks(item["sources"], self.codec)
            )
            evidence = organize(
                item["question"],
                needs,
                sources,
                self.codec,
                self.reranker,
                self.budget,
                self.candidates,
            )
            out["evidence"] = evidence
            if not evidence["sources"]:
                return dict(
                    out,
                    status="abstain",
                    answer="依据不足" if dataset == "university" else "unknown",
                )
            roles = {
                f"R{i}": slot
                for i, slot in enumerate(
                    needs["slots"]
                    or ["Facts and conditions needed to answer the question"]
                )
            }
            payload = {"question": item["question"], "roles": roles, **evidence}
            raw = self.client.complete("binding", protocol.BIND, payload)
            bound = protocol.bindings(raw, roles, evidence)
            out["bindings"] = bound
            payload = {
                "question": item["question"],
                "needs": needs,
                **evidence,
                "bindings": bound,
            }
            if dataset == "finqa":
                raw = self.client.complete("solve", protocol.NUMERIC, payload)
                out["raw_answer"] = raw
                try:
                    out.update(execute(raw, evidence, item["question"]))
                except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                    out.update(status="invalid_plan", error=str(exc))
            elif dataset == "tatqa":
                raw = self.client.complete("solve", protocol.TABLE, payload)
                out["raw_answer"] = raw
                state, answer, scale = parse_table(raw)
                out.update(
                    status={"ok": "answered"}.get(state, state),
                    answer=answer,
                    scale=scale,
                )
            elif dataset == "university":
                available = policy.units(
                    evidence, item["question"], self.codec, self.budget
                )
                raw = self.client.complete(
                    "select",
                    protocol.SELECT,
                    {
                        "question": item["question"],
                        "units": available,
                        "roles": roles,
                        "numbers": evidence["numbers"],
                        "bindings": bound,
                    },
                )
                try:
                    selected = policy.select(raw, available)
                    out["selection_status"] = "selected" if selected else "empty"
                except (ValueError, KeyError, TypeError):
                    selected = []
                    out["selection_status"] = "invalid"
                # The shared fallback uses the original candidate evidence.
                selected = selected or available
                out["selected_units"] = selected
                if not selected:
                    return dict(out, status="abstain", answer="依据不足")
                raw = self.client.complete(
                    "rewrite",
                    protocol.REWRITE,
                    {"question": item["question"], "evidence": selected},
                )
                out["raw_answer"] = raw
                answer = protocol.object_with(raw, ["answer"])["answer"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("invalid policy answer")
                out.update(
                    status="abstain" if answer.strip() == "依据不足" else "answered",
                    answer=answer,
                    source_refs=sorted({u["ref"] for u in selected}),
                )
            else:
                raise ValueError("unsupported dataset")
        except RuntimeError as exc:
            out.update(status="api_error", error=str(exc))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            out.update(status="invalid_format", error=str(exc))
        return out
