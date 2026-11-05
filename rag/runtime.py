from pathlib import Path

import yaml
from qdrant_client import QdrantClient

from rag.index.vector import VectorIndex
from rag.models import OpenEmbedder, OpenReranker
from rag.service import PortfolioService


def build_portfolio(engine, settings):
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / "agent/config.yaml").read_text())
    rag = config["retrieval"]
    encoder = OpenEmbedder(rag["embedding_model"], settings.model_cache_dir)
    reranker = OpenReranker(rag["reranker_model"], settings.model_cache_dir)
    client = QdrantClient(url=settings.qdrant_url, timeout=10, check_compatibility=False)
    return PortfolioService(
        engine,
        encoder,
        VectorIndex(client, model=encoder.name, dimensions=encoder.dimensions),
        reranker,
        correction_threshold=rag.get("correction_threshold", 0.0),
        max_corrections=rag.get("max_corrections", 2),
    )
