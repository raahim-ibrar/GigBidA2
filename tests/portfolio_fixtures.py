"""Deterministic test doubles for control-flow/isolation tests, never retrieval benchmarks."""

import re

from qdrant_client import QdrantClient

from rag.index.vector import VectorIndex
from rag.service import PortfolioService


class FixtureEmbedder:
    name = "fixture-embedding-not-a-real-model"
    dimensions = 4

    def embed(self, texts):
        return [self.query(text) for text in texts]

    def query(self, text):
        words = set(re.findall(r"\w+", text.casefold()))
        return [
            float(bool(words & group))
            for group in (
                {"python", "fastapi", "api"},
                {"design", "brochure", "logo"},
                {"sql", "postgresql", "database"},
                {"java", "spring"},
            )
        ]


class FixtureReranker:
    def score(self, query, texts):
        wanted = set(re.findall(r"\w+", query.casefold()))
        return [
            8.0 if wanted & set(re.findall(r"\w+", text.casefold())) else -10.0 for text in texts
        ]


def portfolio_fixture(engine):
    client = QdrantClient(":memory:", force_disable_check_same_thread=True)
    embedder = FixtureEmbedder()
    return PortfolioService(
        engine,
        embedder,
        VectorIndex(client, model=embedder.name, dimensions=embedder.dimensions),
        FixtureReranker(),
    )
