"""Recover immutable pre/post verifier drafts; judge blinded pairs with the calibrated rubric."""

import argparse
import asyncio
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from agent.graphs.bid_graph import build_bid_graph
from agent.proposal_nodes import sentences
from agent.runtime import checkpoint_serializer
from apps.api.database import make_engine
from apps.api.models import AgentRun, JobRecord
from apps.api.settings import Settings
from evals.judge_adaptive import main as judge


async def extract(root, *, changed=False):
    settings = Settings()
    dsn = (
        make_url(settings.database_url)
        .update_query_dict({"options": "-csearch_path=gigbid_orchestration_gemini_v1"})
        .render_as_string(hide_password=False)
    )
    engine = make_engine(dsn)
    with Session(engine) as db:
        cohort = list(
            db.execute(
                select(AgentRun, JobRecord).join(JobRecord, AgentRun.job_id == JobRecord.id)
            ).all()
        )
    cohort.sort(key=lambda row: (row[1].raw.get("provider_job_id", ""), row[0].id))
    pairs, counts, passes = [], Counter(), []
    async with AsyncPostgresSaver.from_conn_string(
        dsn.replace("postgresql+psycopg://", "postgresql://", 1),
        serde=checkpoint_serializer(),
    ) as saver:
        graph = build_bid_graph(checkpointer=saver)
        for run, job in cohort:
            config = {"configurable": {"thread_id": f"{run.user_id}:{run.id}"}}
            history = [x async for x in graph.aget_state_history(config, limit=100)]
            pending, first = None, True
            for state in reversed(history):
                if state.next == ("verifier",) and state.values.get("draft"):
                    pending = state
                if not pending or state.next != ("critic",):
                    continue
                verification = state.values.get("verification")
                if not verification:
                    continue
                passes.append(
                    {
                        "run_id": run.id,
                        "persona": job.raw.get("category"),
                        "before_checkpoint": pending.config["configurable"]["checkpoint_id"],
                        "after_checkpoint": state.config["configurable"]["checkpoint_id"],
                        "assessed_sentences": verification["assessed_sentences"],
                        "removed_sentences": len(verification["removed"]),
                    }
                )
                persona = job.raw.get("category")
                selected = (
                    (len(verification["removed"]) > 0)
                    if changed
                    else (first and counts[persona] < 3)
                )
                if selected:
                    pair = {"run_id": run.id, "persona": persona, "items": {}}
                    for phase, checkpoint in [("before", pending), ("after", state)]:
                        draft = checkpoint.values["draft"].model_dump(mode="json")
                        key = f"{run.id}:{phase}"
                        if changed:
                            key += ":" + checkpoint.config["configurable"]["checkpoint_id"]
                        identity = hashlib.sha256(key.encode()).hexdigest()[:20]
                        pair["items"][phase] = {
                            "id": identity,
                            "job": job.raw,
                            "evidence": [
                                e.model_dump(mode="json")
                                for e in checkpoint.values.get("evidence", [])
                            ],
                            "proposal": draft,
                            "claims": [
                                {"index": i, "text": text}
                                for i, text in enumerate(
                                    sentences(
                                        draft["text"]
                                        + "\n"
                                        + "\n".join(draft.get("screening_answers", {}).values())
                                    )
                                )
                            ],
                        }
                    pairs.append(pair)
                    counts[persona] += 1
                first = False
                pending = None
    engine.dispose()
    plan = {
        "kind": "Retrospective checkpoint diagnostic; not a new graph/model trial",
        "selection": "First completed verification pass in first three jobs per persona, "
        "sorted by provider job ID then run UUID. Failed/unpaired passes excluded, not successes.",
        "judge": "Same independently calibrated Nvidia rubric; "
        "pair phase hidden and order shuffled.",
        "data_origin": "synthetic",
        "pairs": pairs,
        "all_completed_passes": passes,
        "limits": "Nine-pair descriptive sample; selection requires successful verification. "
        "Verifier rejection counts are self-assessment, not independent truth.",
    }
    if changed:
        plan["selection"] = "All completed verifier passes that actually removed sentences. "
        plan["selection"] += "Exploratory stratum selected by filter activity, not judge scores."
        plan["limits"] = "Retrospective, small changed-draft stratum; no causal population claim. "
        plan["limits"] += "Failed/unpaired verification attempts are not counted as successes."
        if not pairs:
            raise ValueError("No changed pairs exist; do not invent a filtering effect")
    elif len(pairs) != 9:
        raise ValueError(f"Expected three complete pairs per persona; found {dict(counts)}")
    path = root / "pairs.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Checkpoint extraction changed; do not replace frozen pairs")
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


async def main(*, changed=False):
    root = Path(
        "evals/results/verification-changed-v1"
        if changed
        else "evals/results/verification-before-after-v1"
    )
    root.mkdir(parents=True, exist_ok=True)
    plan = await extract(root, changed=changed)
    items = [i for p in plan["pairs"] for i in p["items"].values()]
    random.Random(4016).shuffle(items)
    await judge(items, output=root / "judge")
    labels = {
        r["id"]: r
        for r in map(
            json.loads, (root / "judge/model-labels.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    result = {"pairs": len(plan["pairs"]), "by_phase": {}, "data_origin": "synthetic"}
    result["identical_text_pairs"] = sum(
        p["items"]["before"]["proposal"]["text"] == p["items"]["after"]["proposal"]["text"]
        and p["items"]["before"]["proposal"].get("screening_answers")
        == p["items"]["after"]["proposal"].get("screening_answers")
        for p in plan["pairs"]
    )
    for phase in ["before", "after"]:
        selected = [labels[p["items"][phase]["id"]] for p in plan["pairs"]]
        counts = Counter(c["label"] for p in selected for c in p["labels"])
        factual = counts["supported"] + counts["unsupported"]
        result["by_phase"][phase] = {
            "labels": dict(counts),
            "factual_claims": factual,
            "unsupported_claim_rate": counts["unsupported"] / factual if factual else None,
            "mean_quality": sum(p["quality"] for p in selected) / len(selected),
        }
    result["limits"] = plan["limits"]
    (root / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed", action="store_true")
    args = parser.parse_args()
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as loop:
        loop.run(main(changed=args.changed))
