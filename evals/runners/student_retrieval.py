"""Execute all five production retrievers with real open embeddings and reranking."""

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.database import make_engine
from apps.api.models import Base, EvidenceChunk, PortfolioDocument, User
from evals.contracts import GoldJob, Prediction
from evals.io import write_result
from evals.scoring import rag_scores
from rag.contracts import PortfolioSearch
from rag.index.vector import VectorIndex
from rag.models import OpenEmbedder, OpenReranker
from rag.service import PortfolioService
from scripts.student_personas import TOPICS, cases, documents


def run(output="evals/results/student-retrieval", work="work/retrieval-study"):
    output, work = Path(output), Path(work)
    work.mkdir(parents=True, exist_ok=True)
    engine = make_engine(f"sqlite:///{(work / 'study.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    embedder, reranker = (
        OpenEmbedder(cache_dir="work/models"),
        OpenReranker(cache_dir="work/models"),
    )
    service = PortfolioService(
        engine,
        embedder,
        VectorIndex(QdrantClient(path=str(work / "qdrant")), model=embedder.name, dimensions=384),
        reranker,
    )
    started = time.perf_counter()
    embedder.query("model warmup")
    reranker.score("model warmup", ["model warmup"])
    warmup = time.perf_counter() - started
    cohort, gold = [], []
    try:
        for persona in TOPICS:
            tenant = str(uuid5(NAMESPACE_URL, "student-retrieval:" + persona))
            with Session(engine) as db, db.begin():
                if not db.get(User, tenant):
                    db.add(
                        User(
                            id=tenant,
                            email=f"study-{persona}@example.org",
                            password_hash="disabled",
                        )
                    )
            for document in documents(persona):
                doc = service.ingest(
                    tenant, document["filename"], document["text"].encode(), document["metadata"]
                )
                if doc.status != "ready":
                    service.index_document(tenant, doc.id)
            for case in cases(persona):
                with Session(engine) as db:
                    relevant = list(
                        db.scalars(
                            select(EvidenceChunk.id)
                            .join(PortfolioDocument)
                            .where(
                                PortfolioDocument.user_id == tenant,
                                PortfolioDocument.details["project"].as_string()
                                == case["metadata"].project,
                                PortfolioDocument.details["type"]
                                .as_string()
                                .in_(["case_study", "readme"]),
                            )
                        )
                    )
                query = (
                    f"Help a {case['industry']} team {case['goal']}; "
                    f"implement with {', '.join(case['skills'])}; "
                    "include input validation and reproducible tests."
                )
                row = {"id": case["key"], "tenant": tenant, "persona": persona, "query": query}
                cohort.append(row)
                gold.append(
                    GoldJob(
                        id=row["id"], persona=persona, bid=True, scam=False, relevant_ids=relevant
                    )
                )
            for index, query in enumerate(
                ["Design a cryogenic superconducting magnet", "Draft a notarised land deed"]
            ):
                row = {
                    "id": f"{persona}-unanswerable-{index}",
                    "tenant": tenant,
                    "persona": persona,
                    "query": query,
                }
                cohort.append(row)
                gold.append(GoldJob(id=row["id"], persona=persona, bid=False, scam=False))
        output.mkdir(parents=True, exist_ok=True)
        frozen = json.dumps(cohort, indent=2) + "\n"
        (output / "cohort.json").write_text(frozen, encoding="utf-8")
        (output / "gold.jsonl").write_text(
            "\n".join(row.model_dump_json() for row in gold) + "\n", encoding="utf-8"
        )
        summary = {}
        inputs = {
            "cohort": {"name": "cohort.json", "sha256": hashlib.sha256(frozen.encode()).hexdigest()}
        }
        for variant in ("v0", "v1", "v2", "v3", "v8"):
            predictions, raw, times = [], [], []
            for row in cohort:
                start = time.perf_counter()
                result = service.search(
                    row["tenant"], PortfolioSearch(query=row["query"], k=10, variant=variant)
                )
                elapsed = time.perf_counter() - start
                times.append(elapsed)
                ids = [hit.evidence.id for hit in result.items]
                predictions.append(
                    Prediction(id=row["id"], ranked_ids=ids, elapsed_seconds=elapsed)
                )
                raw.append(
                    {
                        "id": row["id"],
                        "ranked_ids": ids,
                        "scores": [hit.score for hit in result.items],
                        "elapsed_seconds": elapsed,
                        "queries": result.queries,
                        "abstained": result.abstained,
                    }
                )
            (output / f"{variant}-raw.jsonl").write_text(
                "\n".join(json.dumps(row) for row in raw) + "\n", encoding="utf-8"
            )
            summary[variant] = {
                "at_5": rag_scores(gold, predictions, 5),
                "at_10": rag_scores(gold, predictions, 10),
                "p50_seconds": statistics.median(times),
                "p95_seconds": statistics.quantiles(times, n=100, method="inclusive")[94],
            }
            print(f"Measured {variant}: {len(predictions)} queries", flush=True)
        write_result(
            output / "results.json",
            metric="student_retrieval_comparison",
            data_origin="synthetic",
            inputs=inputs,
            results={
                "variants": summary,
                "warmup_seconds": warmup,
                "embedding_model": embedder.name,
                "reranker_model": reranker.name,
                "limitations": (
                    "Controlled synthetic project-identity gold; "
                    "not a human-labelled real-job dev set. "
                    "No inference API charges; CPU/hardware costs not monetised."
                ),
            },
        )
        return summary
    finally:
        service.index.client.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="evals/results/student-retrieval")
    args = parser.parse_args()
    run(args.output)
