"""Replay retrieval on the exact nine proposal-study jobs, using declared synthetic gold."""

import hashlib
import json
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.database import make_engine
from apps.api.models import Base, EvidenceChunk, PortfolioDocument, User
from evals.contracts import GoldJob, Prediction
from evals.scoring import rag_scores
from rag.contracts import PortfolioSearch
from rag.index.vector import VectorIndex
from rag.models import OpenEmbedder, OpenReranker
from rag.service import PortfolioService
from scripts.student_personas import documents

ROOT = Path("evals/results/evaluation-fidelity-v1")
TOPICS = {
    "ai_ml": [["Ticket classification"], ["Document search"], ["Forecast monitoring"]],
    "full_stack": [
        ["Booking portal"],
        ["Commerce dashboard", "Booking portal"],
        ["Team workspace"],
    ],
    "data_analyst": [
        ["Revenue reporting"],
        ["Revenue reporting", "Data quality"],
        ["Data quality"],
    ],
}


def run():
    ROOT.mkdir(parents=True, exist_ok=True)
    source = Path("evals/results/rag-end-to-end-v1/paired-plan.json")
    cohort = json.loads(source.read_text(encoding="utf-8"))["cohort"]
    plan = {
        "job_ids": [r["id"] for r in cohort],
        "relevance_topics": TOPICS,
        "gold_author": "Codex synthetic project-topic annotations, not human gold",
        "gold_rule": "All case-study/README chunks for the named topic, across all industries; "
        "CV and prior proposal chunks are distractors. No industry is specified by these jobs.",
        "query": "Original matcher query: title + newline + description, truncated to 4000",
        "depth": "Recall@5 from k=5; nDCG@10 from k=10. Original generation used k=5.",
        "variants": ["v0", "v3"],
        "data_origin": "synthetic",
        "cohort_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "corpus_generator_sha256": hashlib.sha256(
            Path("scripts/student_personas.py").read_bytes()
        ).hexdigest(),
        "limits": "Retrospective retrieval replay on the same jobs and source corpus; "
        "not a new generation experiment. Topic-family gold can contain more than five "
        "relevant source chunks, so Recall@5 need not approach one.",
    }
    target = ROOT / "retrieval-plan.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8")) != plan:
        raise ValueError("Frozen retrieval plan changed")
    target.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    work = Path("work/fidelity-retrieval")
    work.mkdir(exist_ok=True)
    engine = make_engine("sqlite:///" + (work / "study.sqlite").resolve().as_posix())
    Base.metadata.create_all(engine)
    embedder, reranker = OpenEmbedder(), OpenReranker()
    service = PortfolioService(
        engine,
        embedder,
        VectorIndex(QdrantClient(path=str(work / "qdrant")), model=embedder.name, dimensions=384),
        reranker,
    )
    gold, identity, tenants = [], {}, {}
    try:
        embedder.query("warmup")
        reranker.score("warmup", ["warmup"])
        for persona in TOPICS:
            tenant = str(uuid5(NAMESPACE_URL, "fidelity-retrieval:" + persona))
            tenants[persona] = tenant
            with Session(engine) as db, db.begin():
                if not db.get(User, tenant):
                    db.add(
                        User(
                            id=tenant,
                            email=persona + "@fidelity.example.org",
                            password_hash="disabled",
                        )
                    )
            for document in documents(persona):
                doc = service.ingest(
                    tenant, document["filename"], document["text"].encode(), document["metadata"]
                )
                if doc.status != "ready":
                    service.index_document(tenant, doc.id)
            with Session(engine) as db:
                rows = list(
                    db.execute(
                        select(EvidenceChunk, PortfolioDocument)
                        .join(PortfolioDocument, EvidenceChunk.document_id == PortfolioDocument.id)
                        .where(PortfolioDocument.user_id == tenant)
                    )
                )
                for chunk, doc in rows:
                    identity[chunk.id] = persona + "/" + doc.filename + ":" + str(chunk.ordinal)
                for job in [r for r in cohort if r["category"] == persona]:
                    topics = TOPICS[persona][int(job["id"].rsplit("-", 1)[1])]
                    relevant = [
                        identity[c.id]
                        for c, d in rows
                        if d.details["type"] in {"case_study", "readme"}
                        and any(d.details["project"].startswith("Demo " + t + " /") for t in topics)
                    ]
                    assert relevant
                    gold.append(
                        GoldJob(id=job["id"], persona=persona, relevant_ids=relevant, **job["gold"])
                    )
        (ROOT / "retrieval-gold.jsonl").write_text(
            "".join(g.model_dump_json() + "\n" for g in gold), encoding="utf-8"
        )
        result = {}
        for variant in plan["variants"]:
            ranked = {5: [], 10: []}
            observations = []
            for job in cohort:
                query = (job["title"] + "\n" + job["description"])[:4000]
                for depth in [5, 10]:
                    start = time.perf_counter()
                    hits = service.search(
                        tenants[job["category"]],
                        PortfolioSearch(query=query, k=depth, variant=variant),
                    )
                    ids = [identity[h.evidence.id] for h in hits.items]
                    ranked[depth].append(Prediction(id=job["id"], ranked_ids=ids))
                    observations.append(
                        {
                            "id": job["id"],
                            "depth": depth,
                            "query": query,
                            "ranked_ids": ids,
                            "seconds": time.perf_counter() - start,
                        }
                    )
            (ROOT / f"retrieval-{variant}.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in observations), encoding="utf-8"
            )
            result[variant] = {
                "at_5": rag_scores(gold, ranked[5], 5),
                "at_10": rag_scores(gold, ranked[10], 10),
            }
            print("Same-cohort retrieval completed:", variant, len(cohort), flush=True)
        (ROOT / "retrieval.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        service.index.client.close()
        engine.dispose()


if __name__ == "__main__":
    run()
