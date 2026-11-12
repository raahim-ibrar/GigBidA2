"""Execute matched real ReAct, prebuilt-supervisor and production-graph dev experiments."""

import argparse
import asyncio
import hashlib
import json
import random
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from alembic import command
from alembic.config import Config
from mcp.shared.memory import create_connected_server_and_client_session
from redis.asyncio import Redis
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
from evals.experiments import analyse_arms, assign_arms
from evals.research_architectures import NativeResearchError, policy_violations, run_native
from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter
from mcp_servers.marketplace.factory import create_marketplace_server
from mcp_servers.marketplace.service import MarketplaceService
from mcp_servers.portfolio.factory import create_portfolio_server
from rag.runtime import build_portfolio
from scripts.student_personas import TOPICS, cases
from simulator.app import create_app
from simulator.catalogue import jobs

CONDITIONS = ("react", "supervisor", "hand_graph")
MODELS = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
)


def experiment_plan(
    pilot=False, pilot_model="openai/gpt-oss-120b", conditions=None, study_models=None
):
    study_models = study_models or ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    if pilot:
        cohort = [jobs(seed=4017, per_persona=3)[1]]
    else:
        cohort = jobs(seed=4016, per_persona=17)[:50]
    rng = random.Random(4016)
    model_assignment = {}
    for persona in TOPICS:
        selected = sorted(row["id"] for row in cohort if row["category"] == persona)
        rng.shuffle(selected)
        for i, identity in enumerate(selected):
            model_assignment[identity] = (
                study_models[i % len(study_models)] if not pilot else pilot_model
            )
    for row in cohort:
        row["client_id"] = "independent-" + row["id"]
    strategies = assign_arms(
        [
            {"id": row["id"], "persona": row["category"], "category": row["category"]}
            for row in cohort
        ],
        4016,
    )
    order = {}
    for row in cohort:
        selected_conditions = list(conditions or CONDITIONS)
        rng.shuffle(selected_conditions)
        order[row["id"]] = selected_conditions
    source_paths = sorted(
        {
            *Path("agent").rglob("*.py"),
            *Path("agent/prompts").rglob("*.md"),
            Path("evals/research_architectures.py"),
            Path("evals/research_client.py"),
            Path(__file__).relative_to(Path.cwd()),
            Path("simulator/store.py"),
            Path("agent/config.yaml"),
        }
    )
    return {
        "version": 1,
        "pilot": pilot,
        "seed": 4016,
        "data_origin": "synthetic",
        "jobs": cohort,
        "conditions": list(conditions or CONDITIONS),
        "pilot_model": pilot_model if pilot else None,
        "study_models": study_models if not pilot else None,
        "profile_kind": (
            "optional_closed_model"
            if any(m.startswith("gemini-") for m in model_assignment.values())
            else "open_weight"
        ),
        "condition_order": order,
        "models": model_assignment,
        "strategies": strategies,
        "limits": {
            "max_tokens_per_run": 20000,
            "max_native_graph_steps": 30,
            "max_completion_tokens": {"gpt_oss": 1200, "qwen": 768},
            "critic_revisions": 2,
        },
        "retrieval": "v3, k=3; three indexed fictional case studies per persona",
        "cover_length_target": "60-100 words in every condition",
        "model_control": (
            "Model blocked by job; every architecture sees the same model for that job"
        ),
        "human_approval": (
            "App graph pauses without approval; only separate research simulator scored"
        ),
        "outcomes": (
            "Independent synthetic clients; deterministic rule model, one transaction follow-up"
        ),
        "quality": (
            "Post-hoc independent judge, calibrated on a separate human packet; coverage reported"
        ),
        "x2": "Hand-graph intention-to-treat reply rate by preassigned opening strategy",
        "hypothesis": (
            "Hand graph catches more unsupported claims/policy violations at higher token cost"
        ),
        "known_limits": [
            "Small procedural job families and fictional evidence; "
            "not an independently labelled real-job set",
            "Supervisor uses analyst/writer specialists; "
            "role granularity differs from production graph",
            "Native baselines can choose verification tools; hand graph mandates verification",
            "Shared provider pacing and warm retrieval can affect latency; "
            "order randomized before outcomes",
            "Rule-client reply rates are not real-world effectiveness; "
            "no model quality inferred from tests",
        ],
        "source_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
    }


async def quota_available(settings, model):
    if model.startswith("gemini-"):
        from agent.providers.gemini import GeminiGate

        return await GeminiGate(
            settings.google_api_key.get_secret_value(), settings.redis_url
        ).available(model)
    identity = hashlib.sha256(settings.groq_api_key.get_secret_value().encode()).hexdigest()[:20]
    key = f"gigbid:groq:{identity}:{model}:daily:{int(time.time() // 86400)}"
    async with Redis.from_url(settings.redis_url) as redis:
        used = int(await redis.get(key) or 0)
    # Leave a whole bounded run available; never count an unattempted case as failure.
    return settings.groq_daily_token_cap - used >= 20000


def quota_failure(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        message = str(error).lower()
        if any(s in message for s in ("rate limit", "daily allowance", "token allowance")):
            return True
        error = getattr(error, "cause", None) or getattr(error, "__cause__", None)
    return False


def summarize(plan, rows, output):
    result = {
        "planned_jobs": len(plan["jobs"]),
        "planned_runs": len(plan["jobs"]) * len(plan["conditions"]),
        "recorded_runs": len(rows),
        "complete": len(rows) == len(plan["jobs"]) * len(plan["conditions"]),
        "data_origin": "synthetic",
        "conditions": {},
    }
    gold = {row["id"]: row["gold"]["bid"] for row in plan["jobs"]}
    for condition in CONDITIONS:
        selected = [row for row in rows if row["condition"] == condition]
        measured = [r for r in selected if r["decision"] is not None]
        replies = sum(row["outcome"]["replied"] for row in selected)
        submitted = sum(row["outcome"]["submitted"] for row in selected)
        result["conditions"][condition] = {
            "recorded": len(selected),
            "decisions_measured": len(measured),
            "decision_accuracy_observed": sum(
                (r["decision"] == "bid") == gold[r["id"]] for r in measured
            )
            / len(measured)
            if measured
            else None,
            "decision_accuracy_all_recorded": sum(
                (r["decision"] == "bid") == gold[r["id"]] for r in measured
            )
            / len(selected)
            if selected
            else None,
            "submissions": submitted,
            "replies": replies,
            "reply_rate_per_assigned_job": replies / len(selected) if selected else None,
            "reply_rate_per_submission": replies / submitted if submitted else None,
            "measured_tokens": sum(r["measured_tokens"] for r in selected),
            "tokens_with_unknown_usage": sum(r["unknown_usage_calls"] for r in selected),
            "policy_violations_caught": sum(len(r["policy_violations"]) for r in selected),
            "errors": sum(bool(r["error"]) for r in selected),
            "proposal_quality": (
                "Pending independent calibrated judge; not substituted with gate success"
            ),
        }
    hand = [r for r in rows if r["condition"] == "hand_graph"]
    if len(hand) == len(plan["jobs"]) and not plan["pilot"]:
        result["x2"] = analyse_arms(
            plan["strategies"],
            [
                {"id": r["id"], "replied": r["outcome"]["replied"], "followup_complete": True}
                for r in hand
            ],
        )
    (output / "progress.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


async def run(
    output,
    study_id,
    *,
    pilot=False,
    max_new=None,
    pilot_model="openai/gpt-oss-120b",
    conditions=None,
    study_models=None,
):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if conditions and not pilot:
        raise ValueError("Subset debugging is allowed only for the separate pilot")
    plan = experiment_plan(pilot, pilot_model, conditions, study_models)
    plan_path = output / "plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError("Frozen plan/source differs; keep the old run and use a new study ID")
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    raw_path = output / "runs.jsonl"
    rows = [json.loads(s) for s in raw_path.read_text().splitlines()] if raw_path.exists() else []
    done = {(r["id"], r["condition"]) for r in rows}
    settings = Settings()
    admin = make_engine(settings.database_url)
    if not study_id.replace("_", "").isalnum() or len(study_id) > 24:
        raise ValueError("Invalid isolated study ID")
    schema = "gigbid_orchestration_" + study_id
    with admin.begin() as conn:
        conn.execute(CreateSchema(schema, if_not_exists=True))
    url = make_url(settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    settings = settings.model_copy(
        update={
            "database_url": url.update_query_dict(
                {"options": "-csearch_path=" + schema}
            ).render_as_string(hide_password=False)
        }
    )
    engine = make_engine(settings.database_url)
    migration = Config("alembic.ini")
    with engine.begin() as conn:
        migration.attributes["connection"] = conn
        command.upgrade(migration, "head")
    await asyncio.to_thread(ensure_storage, settings.database_url)
    portfolio = build_portfolio(engine, settings)
    catalogue = output / "cohort.json"
    catalogue.write_text(json.dumps(plan["jobs"]), encoding="utf-8")
    sim = create_app(
        output / "simulator.sqlite",
        api_key="research-only",
        catalogue_path=catalogue,
        starting_connects=10000,
    )
    store, accounts, prepared = RunStore(engine), MarketplaceAccounts(engine, settings), set()
    new = 0
    try:
        for raw in plan["jobs"]:
            for condition in plan["condition_order"][raw["id"]]:
                if (raw["id"], condition) in done:
                    continue
                if max_new is not None and new >= max_new:
                    summarize(plan, rows, output)
                    return
                model, persona = plan["models"][raw["id"]], raw["category"]
                if not await quota_available(settings, model):
                    print(f"PENDING quota: {model} {raw['id']} {condition}", flush=True)
                    continue
                tenant = str(uuid5(NAMESPACE_URL, f"{study_id}:research:{persona}"))
                if persona not in prepared:
                    with Session(engine) as db, db.begin():
                        if not db.get(User, tenant):
                            db.add(
                                User(
                                    id=tenant,
                                    email=f"{study_id}-{persona}@example.org",
                                    password_hash="disabled-research",
                                )
                            )
                            db.flush()
                            db.add(
                                FreelancerProfile(
                                    user_id=tenant, persona=persona, weekly_connects_budget=10000
                                )
                            )
                    accounts.set_mode(tenant, "student_sim")
                    for source in list(cases(persona))[:3]:
                        doc = await asyncio.to_thread(
                            portfolio.ingest,
                            tenant,
                            source["filename"],
                            source["text"].encode(),
                            source["metadata"],
                        )
                        if doc.status != "ready":
                            await asyncio.to_thread(portfolio.index_document, tenant, doc.id)
                    prepared.add(persona)
                adapter = StudentSimAdapter(
                    "http://research",
                    "research-only",
                    tenant,
                    transport=httpx.ASGITransport(app=sim),
                )
                job = accounts.import_job(tenant, {k: v for k, v in raw.items() if k != "gold"})
                key = str(uuid5(NAMESPACE_URL, f"{study_id}:{condition}:{raw['id']}"))
                app_run = store.create_run(tenant, job.id, key)
                if (
                    app_run.status == "needs_attention"
                    and app_run.retryable
                    and quota_failure(app_run.error)
                ):
                    app_run = store.retry(tenant, app_run.id, app_run.version)
                with Session(engine) as db, db.begin():
                    r = db.get(AgentRun, app_run.id)
                    if r.status == "queued":
                        r.snapshot = {
                            **r.snapshot,
                            "proposal_strategy": plan["strategies"][raw["id"]],
                        }
                market_server = create_marketplace_server(
                    MarketplaceService(engine, settings, tenant, app_run.id, adapter=adapter),
                    tenant,
                    app_run.id,
                )
                config = AgentConfig(
                    profile_name="paid" if model.startswith("gemini-") else "hosted_open"
                )
                config.models = {role: model for role in config.models}
                config.fallback = None
                config.budgets.max_tokens_per_thread = 20000
                config.output_tokens = 768 if model.startswith("qwen/") else 1200
                if model.startswith("gemini-"):
                    config.output_tokens = 2000
                config.prompts["writer"] = config.prompts["writer"].replace(
                    "about 120-220 words", "about 60-100 words"
                )
                config.retrieval = {**config.retrieval, "top_k": 3}
                usage, calls, candidate, error, state = [], [], None, None, {}
                start = time.perf_counter()
                async with (
                    create_connected_server_and_client_session(market_server) as ms,
                    create_connected_server_and_client_session(
                        create_portfolio_server(portfolio, tenant)
                    ) as ps,
                ):
                    market, reader = MarketplaceMCP(ms), PortfolioMCP(ps)
                    if condition == "hand_graph":
                        await process_run(
                            engine,
                            settings,
                            tenant,
                            app_run.id,
                            config=config,
                            portfolio_reader=reader,
                            marketplace_reader=market,
                        )
                        saved = store.run(tenant, app_run.id)
                        state = saved.snapshot.model_dump(mode="json")
                        error = saved.error
                        if quota_failure(error):
                            print("PENDING provider quota; saved checkpoint retained", flush=True)
                            return
                        candidate = {
                            "action": state.get("decision", {}).get("action")
                            if state.get("decision")
                            else None,
                            "risk_score": state.get("risk", {}).get("score")
                            if state.get("risk")
                            else None,
                            "price": state.get("price", {}).get("amount")
                            if state.get("price")
                            else None,
                            "text": state.get("draft", {}).get("text", "")
                            if state.get("draft")
                            else "",
                            "screening_answers": state.get("draft", {}).get("screening_answers", {})
                            if state.get("draft")
                            else {},
                        }
                        with Session(engine) as db:
                            usage = [
                                e.details
                                for e in db.scalars(
                                    select(RunEvent).where(
                                        RunEvent.run_id == app_run.id,
                                        RunEvent.kind == "model_usage",
                                    )
                                )
                            ]
                    else:
                        try:
                            got, usage, calls = await run_native(
                                condition,
                                settings,
                                model,
                                config,
                                raw,
                                reader,
                                market,
                                plan["strategies"][raw["id"]],
                            )
                            candidate = got.model_dump()
                        except NativeResearchError as failure:
                            if quota_failure(failure):
                                print(
                                    "PENDING provider quota; native case remains unrecorded",
                                    flush=True,
                                )
                                return
                            error, usage, calls = str(failure), failure.usage, failure.calls
                            candidate = (
                                failure.candidate.model_dump() if failure.candidate else None
                            )
                    elapsed = time.perf_counter() - start
                    evidence = [
                        e.model_dump()
                        for e in await reader.search(
                            raw["title"] + "\n" + raw["description"], k=3, variant="v3"
                        )
                    ]
                candidate = candidate or {}
                text = candidate.get("text", "")
                violations = policy_violations(
                    text + "\n" + "\n".join(candidate.get("screening_answers", {}).values())
                )
                outcome = {
                    "submitted": False,
                    "replied": False,
                    "hired": False,
                    "source": "student_sim",
                    "followup_complete": True,
                }
                ready = (
                    not error
                    and candidate.get("action") == "bid"
                    and text
                    and not violations
                    and candidate.get("price")
                    and (condition != "hand_graph" or saved.status == "awaiting_approval")
                )
                if ready:
                    scoring_tenant = str(
                        uuid5(NAMESPACE_URL, f"score:{study_id}:{condition}:{raw['id']}")
                    )
                    scorer = StudentSimAdapter(
                        "http://research",
                        "research-only",
                        scoring_tenant,
                        transport=httpx.ASGITransport(app=sim),
                    )
                    effect = await scorer.submit_proposal(
                        ProposalWrite(
                            job_id=raw["id"],
                            text=text,
                            screening_answers=candidate.get("screening_answers", {}),
                            bid_amount=candidate["price"],
                            idempotency_key=f"research:{key}",
                            dry_run=False,
                        )
                    )
                    stages = {
                        e["stage"]
                        for e in sim.state.store.events(scoring_tenant)
                        if e["proposal_id"] == effect.data["id"]
                    }
                    outcome.update(
                        submitted=True,
                        replied="replied" in stages,
                        hired="hired" in stages,
                        receipt=effect.data,
                        event_id=f"research:{key}",
                    )
                row = {
                    "id": raw["id"],
                    "condition": condition,
                    "persona": persona,
                    "model": model,
                    "strategy": plan["strategies"][raw["id"]],
                    "decision": candidate.get("action"),
                    "candidate": candidate,
                    "job": {k: v for k, v in raw.items() if k != "gold"},
                    "evidence": evidence,
                    "snapshot": state,
                    "usage": usage,
                    "tool_calls": calls,
                    "elapsed_seconds": elapsed,
                    "policy_violations": violations,
                    "error": error,
                    "measured_tokens": sum(
                        u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in usage
                    ),
                    "unknown_usage_calls": sum(u.get("usage_known") is False for u in usage),
                    "outcome": outcome,
                }
                with raw_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=True) + "\n")
                rows.append(row)
                done.add((raw["id"], condition))
                new += 1
                summarize(plan, rows, output)
                print(
                    f"{raw['id']} {condition}: {row['decision']}, error={error}, "
                    f"tokens={row['measured_tokens']}, {elapsed:.1f}s",
                    flush=True,
                )
    finally:
        summarize(plan, rows, output)
        portfolio.index.client.close()
        engine.dispose()
        admin.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="evals/results/student-orchestration-v1")
    parser.add_argument("--study-id", default="v1")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--max-new", type=int)
    parser.add_argument("--pilot-model", choices=MODELS, default="openai/gpt-oss-120b")
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS)
    parser.add_argument(
        "--models", nargs="+", choices=MODELS, default=["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    )
    args = parser.parse_args()
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(
            run(
                args.output,
                args.study_id,
                pilot=args.pilot,
                max_new=args.max_new,
                pilot_model=args.pilot_model,
                conditions=args.conditions,
                study_models=args.models,
            )
        )
