import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langsmith import Client
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from agent.tracing import build_spans, export_run
from apps.api.database import make_engine
from apps.api.models import AgentRun, JobRecord, RunEvent
from apps.api.settings import Settings

p = Path("work/public-demo")
rows = json.loads((p / "new-trace-runs.json").read_text())
s = Settings()
s = s.model_copy(
    update={
        "database_url": make_url(s.database_url)
        .update_query_dict({"options": "-csearch_path=gigbid_public_demo_20261112"})
        .render_as_string(hide_password=False),
        "trace_export_enabled": True,
    }
)
engine = make_engine(s.database_url)
c = Client(
    api_key=s.langsmith_api_key.get_secret_value(),
    api_url="https://api.smith.langchain.com",
    auto_batch_tracing=False,
)
public = []
for row in rows:
    with Session(engine) as db:
        run = db.scalar(
            select(AgentRun).where(
                AgentRun.id == row["run_id"],
                AgentRun.user_id == "54917dde-fdaf-44a8-8311-c7f6ffbd5b18",
            )
        )
        assert run
        job = db.get(JobRecord, run.job_id)
        assert job.raw["source"] == "student_sim" and job.raw["provider_job_id"].startswith(
            "student-4016-"
        )
        print(row["kind"], run.id, run.status, run.steps, run.tokens, flush=True)
        if run.status in ["queued", "running"]:
            continue
        events = list(
            db.scalars(select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id))
        )
        spans = build_spans(run, [e for e in events if not e.kind.startswith("trace_")])
        counts = {k: sum(s["run_type"] == k for s in spans) for k in ["chain", "llm", "tool"]}
        assert counts["llm"] and counts["tool"]
        exported = export_run(engine, s, run.user_id, run.id, client=c)
        remote_id = exported["remote_trace_id"]
        for attempt in range(12):
            try:
                remote = c.read_run(remote_id)
                break
            except Exception:
                if attempt == 11:
                    raise
                time.sleep(3)
        assert str(remote.trace_id) == remote_id
        url = next(
            (
                e.details["url"]
                for e in events
                if e.kind == "trace_shared" and e.details.get("remote_trace_id") == remote_id
            ),
            None,
        ) or c.share_run(remote_id)
        if not any(
            e.kind == "trace_shared" and e.details.get("remote_trace_id") == remote_id
            for e in events
        ):
            db.add(
                RunEvent(
                    run_id=run.id,
                    kind="trace_shared",
                    details={
                        "url": url,
                        "remote_trace_id": remote_id,
                        "data_origin": "synthetic",
                        "policy": exported["policy"],
                    },
                )
            )
            db.commit()
        public.append(
            {
                "kind": row["kind"],
                "run_id": run.id,
                "remote_trace_id": remote_id,
                "status": run.status,
                "url": url,
                "spans": counts,
                "data_origin": "synthetic",
                "privacy": "Metadata only; no prompts, CV, tool arguments/results or credentials",
            }
        )
destination = Path("evals/results/public-traces.json")
existing = (
    json.loads(destination.read_text(encoding="utf-8"))["traces"] if destination.exists() else []
)
merged = {row["run_id"]: row for row in existing}
merged.update({row["run_id"]: row for row in public})
destination.write_text(
    json.dumps({"complete": len(public) == 3, "traces": list(merged.values())}, indent=2),
    encoding="utf-8",
)
print(json.dumps(public, indent=2))
