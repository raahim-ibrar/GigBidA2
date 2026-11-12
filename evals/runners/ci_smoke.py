"""Fresh 30-job deterministic control evaluation, not an LLM quality experiment.

Runs production graphs, tenant-bound MCP, approval transactions and simulator outcomes.
No API keys, GPU, recorded predictions or hidden data are used. Model-sensitive research
remains a separately measured cohort; this smoke catches application-control regressions.
"""

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from agent.config import AgentConfig
from agent.marketplace_client import MarketplaceMCP
from agent.persistence import ensure_storage
from agent.portfolio_client import PortfolioMCP
from agent.run_store import RunStore
from agent.runtime import process_run
from apps.api.database import make_engine
from apps.api.marketplace import MarketplaceAccounts
from apps.api.models import FreelancerProfile, User
from apps.api.schemas.proposals import ReviewRun
from apps.api.settings import Settings
from evals.contracts import GoldJob, Outcome, Prediction
from evals.runners.suite import evaluate_bundle
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter
from mcp_servers.marketplace.factory import create_marketplace_server
from mcp_servers.marketplace.service import MarketplaceService
from mcp_servers.portfolio.factory import create_portfolio_server
from rag.contracts import DocumentMetadata, PortfolioSearch
from simulator.app import create_app
from tests.portfolio_fixtures import portfolio_fixture
from tests.proposal_fixtures import BrowserModels


async def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    base = Settings()
    schema = "gigbid_ci_" + uuid4().hex
    admin = make_engine(base.database_url)
    with admin.begin() as db:
        db.execute(CreateSchema(schema))
    database = (
        make_url(base.database_url)
        .update_query_dict({"options": "-csearch_path=" + schema})
        .render_as_string(hide_password=False)
    )
    settings = base.model_copy(update={"database_url": database, "trace_export_enabled": False})
    engine = make_engine(database)
    migration = Config("alembic.ini")
    with engine.begin() as db:
        migration.attributes["connection"] = db
        command.upgrade(migration, "head")
    await asyncio.to_thread(ensure_storage, database)
    portfolio = portfolio_fixture(engine)
    store = RunStore(engine)
    accounts = MarketplaceAccounts(engine, settings)
    config = AgentConfig(profile_name="open")
    config.retrieval = {**config.retrieval, "variant": "v0"}
    gold = []
    predictions = []
    outcomes = []
    observations = []
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="gigbid-ci-") as temp:
            sim = create_app(Path(temp) / "sim.sqlite", api_key="ci-control-only", per_persona=10)
            # Transparent control cohort: the same simple API task across three isolated
            # personas, with the catalogue's negative controls retained. Not research data.
            for row in sim.state.store.jobs.values():
                row["required_skills"] = ["Python", "API"]
                if row["gold"]["bid"]:
                    row["title"] = "Python API for synthetic project " + row["id"][-3:]
                    row["description"] = (
                        "Build a Python API. Include tests, assumptions and a handover."
                    )
            for persona in ["ai_ml", "full_stack", "data_analyst"]:
                tenant = str(uuid4())
                with Session(engine) as db, db.begin():
                    db.add(
                        User(
                            id=tenant,
                            email=f"ci-{persona}-{tenant}@example.org",
                            password_hash="disabled-control-login",
                        )
                    )
                    db.flush()
                    db.add(
                        FreelancerProfile(
                            user_id=tenant, persona=persona, weekly_connects_budget=100
                        )
                    )
                accounts.set_mode(tenant, "student_sim")
                source = portfolio.ingest(
                    tenant,
                    "ci-source.md",
                    b"I built a Python API.",
                    DocumentMetadata(
                        type="case_study", project="CI synthetic control", skills=["Python", "API"]
                    ),
                )
                portfolio.index_document(tenant, source.id)
                evidence = (
                    portfolio.search(tenant, PortfolioSearch(query="Python API")).items[0].evidence
                )
                adapter = StudentSimAdapter(
                    "http://sim", "ci-control-only", tenant, transport=httpx.ASGITransport(app=sim)
                )
                for raw in [r for r in sim.state.store.jobs.values() if r["category"] == persona]:
                    job = accounts.import_job(tenant, {k: v for k, v in raw.items() if k != "gold"})
                    current = store.create_run(tenant, job.id, str(uuid4()))
                    stamp = time.perf_counter()

                    async def process():
                        marketplace = create_marketplace_server(
                            MarketplaceService(
                                engine, settings, tenant, current.id, adapter=adapter
                            ),
                            tenant,
                            current.id,
                        )
                        async with create_connected_server_and_client_session(marketplace) as ms:
                            async with create_connected_server_and_client_session(
                                create_portfolio_server(portfolio, tenant)
                            ) as ps:
                                return await process_run(
                                    engine,
                                    settings,
                                    tenant,
                                    current.id,
                                    models_factory=BrowserModels,
                                    portfolio_reader=PortfolioMCP(ps),
                                    marketplace_reader=MarketplaceMCP(ms),
                                    config=config,
                                )

                    await process()
                    current = store.run(tenant, current.id)
                    if current.status == "awaiting_approval":
                        store.review(
                            tenant,
                            ReviewRun(
                                run_id=current.id,
                                version=current.version,
                                action="approve",
                                draft_digest=current.review["preview"]["arguments"]["draft_digest"],
                            ),
                        )
                        await process()
                        current = store.run(tenant, current.id)
                    state = current.snapshot
                    sent = current.status == "submitted"
                    stages = sim.state.store.events(tenant)
                    # Event payloads are keyed by proposal, so also read the actual write receipt.
                    with sim.state.store.db() as db:
                        found = (
                            db.execute(
                                "SELECT id FROM proposals WHERE tenant=? AND job_id=?",
                                (tenant, raw["id"]),
                            ).fetchone()
                            if sent
                            else None
                        )
                    events = [r for r in stages if found and r.get("proposal_id") == found["id"]]
                    gold.append(
                        GoldJob(
                            id=raw["id"], persona=persona, relevant_ids=[evidence.id], **raw["gold"]
                        ).model_dump()
                    )
                    predictions.append(
                        Prediction(
                            id=raw["id"],
                            bid=bool(state.decision and state.decision.action == "bid"),
                            scam=bool(
                                state.risk and state.risk.score >= config.policy["maximum_risk"]
                            ),
                            ranked_ids=[e.id for e in state.evidence],
                            price=state.price.amount if state.price else None,
                            claim_labels=[
                                "supported" if c.verdict == "supported" else "unsupported"
                                for c in (state.draft.claims if state.draft else [])
                                if c.kind == "experience"
                            ],
                            claim_label_source="deterministic-control exact source; not a judge",
                            measured_tokens=0,
                            elapsed_seconds=time.perf_counter() - stamp,
                        ).model_dump()
                    )
                    outcomes.append(
                        Outcome(
                            id=raw["id"],
                            event_id="ci:" + current.id,
                            source="student_sim",
                            submitted=sent,
                            replied=any(r["stage"] == "replied" for r in events),
                            hired=any(r["stage"] == "hired" for r in events),
                            connects=raw["connects_cost"] if sent else None,
                            followup_complete=True,
                        ).model_dump()
                    )
                    observations.append(
                        {
                            "id": raw["id"],
                            "status": current.status,
                            "error": current.error,
                            "steps": current.steps,
                            "approval_actor": "automated CI control, not a human",
                        }
                    )
                    print(len(observations), "/30", current.status, flush=True)
        for name, rows in [
            ("gold", gold),
            ("predictions", predictions),
            ("outcomes", outcomes),
            ("observations", observations),
        ]:
            (output / (name + ".jsonl")).write_text(
                "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
            )
        manifest = {
            "data_origin": "synthetic",
            "gold": "gold.jsonl",
            "predictions": "predictions.jsonl",
            "outcomes": "outcomes.jsonl",
            "experiment_id": "fresh-ci-control-30",
            "min_cases": 30,
            "bid_f1_floor": 0.98,
            "unsupported_claim_rate_ceiling": 0,
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        gate = evaluate_bundle(output / "manifest.json", output / "metrics")
        retrieval = json.loads((output / "metrics/retrieval.json").read_text(encoding="utf-8"))
        recall = retrieval["results"]["overall"]["macro_recall_at_k"]
        submitted = sum(r["submitted"] for r in outcomes)
        replied = sum(r["replied"] for r in outcomes)
        reply_rate = replied / submitted if submitted else 0
        checks = {
            "decision_and_grounding_gate": gate["results"]["passed"],
            "all_runs_terminal": all(r["status"] in ["skip", "submitted"] for r in observations),
            "recall_at_5_floor_095": recall is not None and recall >= 0.95,
            "reply_rate_floor_095": reply_rate >= 0.95,
        }
        summary = {
            "kind": "fresh deterministic application-control smoke, not LLM quality research",
            "jobs": len(gold),
            "passed": all(checks.values()),
            "checks": checks,
            "recall_at_5": recall,
            "reply_rate": reply_rate,
            "submitted": submitted,
            "replied": replied,
            "elapsed_seconds": time.perf_counter() - started,
            "model_api_calls": 0,
            "usd_api": 0,
            "limits": "Deterministic role/embedding fixtures; not prompt or model quality.",
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if not summary["passed"]:
            raise RuntimeError("CI control quality gate failed; inspect generated observations")
        return summary
    finally:
        portfolio.index.client.close()
        engine.dispose()
        with admin.begin() as db:
            db.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evals/results/ci-smoke")
    args = parser.parse_args()
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as loop:
        print(json.dumps(loop.run(run(args.output))))


if __name__ == "__main__":
    main()
