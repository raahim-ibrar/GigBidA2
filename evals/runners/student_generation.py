"""Real open-model graph comparison. Isolated research candidates never authorize app sends."""

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from alembic import command
from alembic.config import Config
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from agent.config import AgentConfig
from agent.marketplace_client import MarketplaceMCP
from agent.marketplace_port import ProposalWrite
from agent.persistence import ensure_storage
from agent.portfolio_client import PortfolioMCP
from agent.run_store import RunStore
from agent.runtime import process_run
from apps.api.database import make_engine
from apps.api.marketplace import MarketplaceAccounts
from apps.api.models import AgentRun, FreelancerProfile, RunEvent, User
from apps.api.settings import Settings
from evals.contracts import GoldJob, Outcome, Prediction
from evals.experiments import analyse_arms, assign_arms
from evals.scoring import decision_scores
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter
from mcp_servers.marketplace.factory import create_marketplace_server
from mcp_servers.marketplace.service import MarketplaceService
from mcp_servers.portfolio.factory import create_portfolio_server
from rag.runtime import build_portfolio
from scripts.student_personas import TOPICS, documents
from simulator.app import create_app


async def run(models, per_persona, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    schema = "gigbid_student_generation_v3"
    admin = make_engine(settings.database_url)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema, if_not_exists=True))
    url = make_url(settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    settings = settings.model_copy(
        update={
            "database_url": url.update_query_dict(
                {"options": f"-csearch_path={schema}"}
            ).render_as_string(hide_password=False)
        }
    )
    engine = make_engine(settings.database_url)
    migration = Config("alembic.ini")
    with engine.begin() as connection:
        migration.attributes["connection"] = connection
        command.upgrade(migration, "head")
    await asyncio.to_thread(ensure_storage, settings.database_url)
    portfolio = build_portfolio(engine, settings)
    sim = create_app(output / "simulator.sqlite", api_key="research-only", per_persona=per_persona)
    cohort = list(sim.state.store.jobs.values())
    assignments = assign_arms(
        [
            {"id": row["id"], "persona": row["category"], "category": row["category"]}
            for row in cohort
        ],
        4016,
    )
    plan = {
        "schema": schema,
        "models": models,
        "job_ids": [row["id"] for row in cohort],
        "assignments": assignments,
        "seed": 4016,
        "data_origin": "synthetic",
        "purpose": "Research-only candidate scoring, not approved application submissions",
        "client_model": "declared deterministic rule model",
        "followup": "one simulator transaction",
        "limits": "Uncalibrated model claim checks; human calibration/panel not collected",
        "source_hashes": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted([*Path("agent").glob("*.py"), *Path("agent/prompts").glob("*.md")])
        },
        "configuration": AgentConfig().data,
    }
    plan_path = output / "plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Frozen study plan differs; use a new output directory")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    store, accounts = RunStore(engine), MarketplaceAccounts(engine, settings)
    try:
        for model in models:
            config = AgentConfig()
            config.models = {role: model for role in config.models}
            config.fallback = None  # Compare the declared models without hidden fallback.
            config.budgets.max_tokens_per_thread = 32000
            config.timeout = 180
            config.retrieval = {**config.retrieval, "variant": "v0"}
            label = model.replace(":", "-").replace("/", "-")
            target = output / f"{label}.jsonl"
            recorded = (
                [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
                if target.exists()
                else []
            )
            done = {row["id"] for row in recorded}
            for persona in TOPICS:
                tenant = str(uuid5(NAMESPACE_URL, f"research-v3:{model}:{persona}"))
                with Session(engine) as db, db.begin():
                    if not db.get(User, tenant):
                        db.add(
                            User(
                                id=tenant,
                                email=f"{label}-{persona}@example.org",
                                password_hash="disabled-research",
                            )
                        )
                        db.flush()
                        db.add(
                            FreelancerProfile(
                                user_id=tenant,
                                display_name="Synthetic research persona",
                                persona=persona,
                            )
                        )
                accounts.set_mode(tenant, "student_sim")
                for document in documents(persona):
                    doc = await asyncio.to_thread(
                        portfolio.ingest,
                        tenant,
                        document["filename"],
                        document["text"].encode(),
                        document["metadata"],
                    )
                    if doc.status != "ready":
                        await asyncio.to_thread(portfolio.index_document, tenant, doc.id)
                adapter = StudentSimAdapter(
                    "http://research",
                    "research-only",
                    tenant,
                    transport=httpx.ASGITransport(app=sim),
                )
                for raw in [row for row in cohort if row["category"] == persona]:
                    if raw["id"] in done:
                        continue
                    job = accounts.import_job(tenant, {k: v for k, v in raw.items() if k != "gold"})
                    key = str(uuid5(NAMESPACE_URL, f"research:{model}:{raw['id']}"))
                    run = store.create_run(tenant, job.id, key)
                    if run.status == "queued":
                        with Session(engine) as db, db.begin():
                            row = db.get(AgentRun, run.id)
                            row.snapshot = {
                                **row.snapshot,
                                "proposal_strategy": assignments[raw["id"]],
                            }
                    market_server = create_marketplace_server(
                        MarketplaceService(engine, settings, tenant, run.id, adapter=adapter),
                        tenant,
                        run.id,
                    )
                    portfolio_server = create_portfolio_server(portfolio, tenant)
                    start = time.perf_counter()
                    async with (
                        create_connected_server_and_client_session(market_server) as market_session,
                        create_connected_server_and_client_session(
                            portfolio_server
                        ) as portfolio_session,
                    ):
                        await process_run(
                            engine,
                            settings,
                            tenant,
                            run.id,
                            config=config,
                            portfolio_reader=PortfolioMCP(portfolio_session),
                            marketplace_reader=MarketplaceMCP(market_session),
                        )
                    elapsed = time.perf_counter() - start
                    run = store.run(tenant, run.id)
                    state = run.snapshot
                    submitted, replied, hired, connects = False, False, False, None
                    # Separate research scoring of a frozen candidate. Do not forge an app
                    # ApprovalAudit or resume its human interrupt. This tenant is research-only.
                    if run.status == "awaiting_approval" and state.draft and state.price:
                        effect = await adapter.submit_proposal(
                            ProposalWrite(
                                job_id=raw["id"],
                                text=state.draft.text,
                                screening_answers=state.draft.screening_answers,
                                bid_amount=state.price.amount,
                                idempotency_key=f"research:{key}",
                                dry_run=False,
                            )
                        )
                        stages = [
                            item["stage"]
                            for item in sim.state.store.events(tenant)
                            if item["proposal_id"] == effect.data["id"]
                        ]
                        submitted, replied, hired = True, "replied" in stages, "hired" in stages
                        connects = effect.data["connects_spent"]
                    with Session(engine) as db:
                        usage = [
                            event.details
                            for event in db.scalars(
                                select(RunEvent).where(
                                    RunEvent.run_id == run.id, RunEvent.kind == "model_usage"
                                )
                            )
                        ]
                    prediction = Prediction(
                        id=raw["id"],
                        bid=bool(state.decision and state.decision.action == "bid"),
                        scam=bool(state.risk and state.risk.score >= config.policy["maximum_risk"]),
                        ranked_ids=[item.id for item in state.evidence],
                        price=state.price.amount if state.price else None,
                        measured_tokens=sum(
                            item.get("input_tokens", 0) + item.get("output_tokens", 0)
                            for item in usage
                        ),
                        elapsed_seconds=elapsed,
                    )
                    result = {
                        "id": raw["id"],
                        "persona": persona,
                        "strategy": assignments[raw["id"]],
                        "run_id": run.id,
                        "status": run.status,
                        "error": run.error,
                        "gold": GoldJob(id=raw["id"], persona=persona, **raw["gold"]).model_dump(),
                        "prediction": prediction.model_dump(),
                        "snapshot": state.model_dump(mode="json"),
                        "usage": usage,
                        "outcome": Outcome(
                            id=raw["id"],
                            event_id=f"research:{key}",
                            source="student_sim",
                            submitted=submitted,
                            replied=replied,
                            hired=hired,
                            connects=connects,
                            followup_complete=True,
                        ).model_dump(),
                    }
                    with target.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                    recorded.append(result)
                    print(f"{model} {raw['id']}: {run.status}, {elapsed:.1f}s", flush=True)
            scores = decision_scores(
                [GoldJob.model_validate(row["gold"]) for row in recorded],
                [Prediction.model_validate(row["prediction"]) for row in recorded],
            )
            (output / f"{label}-summary.json").write_text(
                json.dumps(
                    {
                        "model": model,
                        "data_origin": "synthetic",
                        "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                        "scores": scores,
                        "x2": analyse_arms(
                            assignments,
                            [
                                {
                                    "id": row["id"],
                                    "replied": row["outcome"]["replied"],
                                    "followup_complete": True,
                                }
                                for row in recorded
                            ],
                        ),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
    finally:
        portfolio.index.client.close()
        engine.dispose()
        admin.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["qwen3.5:4b", "qwen3:8b"])
    parser.add_argument("--per-persona", type=int, default=10)
    parser.add_argument("--output", default="work/generation-study-v3")
    args = parser.parse_args()
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(run(args.models, args.per_persona, args.output))
