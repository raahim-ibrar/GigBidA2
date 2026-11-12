"""Small paired V0/V3 diagnostic; never pools outcomes with the 150-run study."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

from agent.config import AgentConfig
from evals.runners.student_generation import run
from simulator.catalogue import jobs


async def main():
    root = Path(os.getenv("GIGBID_RAG_E2E_OUTPUT", "evals/results/rag-end-to-end-v1"))
    root.mkdir(parents=True, exist_ok=True)
    config = AgentConfig(profile_name="hosted_open")
    plan = {
        "hypothesis": "V3 improves grounded completion and simulated replies over V0.",
        "design": "Nine identical jobs per variant: three per persona, three scam controls.",
        "primary_metric": "Simulator replies per assigned job (intention to treat)",
        "secondary": ["bid F1", "scam precision/recall", "fair price band", "latency", "tokens"],
        "variants": ["v0", "v3"],
        "cohort": jobs(seed=4016, per_persona=3),
        "configuration": config.data,
        "token_budget": 32000,
        "seed": 4016,
        "data_origin": "synthetic",
        "real_model_calls": True,
        "gpu_inference": False,
        "approval": "Research-only rule-client scoring; no human approval or real sends claimed.",
        "limits": "Small reused development cohort, not a held-out confirmatory result. "
        "Generation is nondeterministic even at temperature zero. No paid fallback.",
        "sources": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ["agent", "rag", "mcp_servers", "simulator"]
            for p in sorted(Path(folder).rglob("*.py"))
        },
    }
    target = root / "paired-plan.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != plan:
        raise ValueError("Frozen plan differs; do not overwrite the experiment")
    target.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    for variant in plan["variants"]:
        await run(
            ["routed"],
            3,
            root / variant,
            profile="hosted_open",
            study_id="rag_e2e_" + variant,
            retrieval_variant=variant,
        )


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as loop:
        loop.run(main())
