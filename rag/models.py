"""CPU open models, loaded lazily and cached outside the user's home directory."""

from functools import lru_cache
from pathlib import Path


class OpenEmbedder:
    dimensions = 384

    def __init__(self, name="BAAI/bge-small-en-v1.5", cache_dir=None):
        if name != "BAAI/bge-small-en-v1.5":
            raise ValueError("Configure a supported embedding model and its dimensions together")
        self.name = name
        self.cache_dir = str(cache_dir or Path(__file__).resolve().parents[1] / "work/models")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [value.tolist() for value in _encoder(self.name, self.cache_dir).embed(texts)]

    def query(self, text: str) -> list[float]:
        return next(_encoder(self.name, self.cache_dir).query_embed(text)).tolist()


@lru_cache(maxsize=2)
def _encoder(name, cache_dir):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name, cache_dir=cache_dir, threads=2)


class OpenReranker:
    def __init__(self, name="Xenova/ms-marco-MiniLM-L-6-v2", cache_dir=None):
        self.name = name
        self.cache_dir = str(cache_dir or Path(__file__).resolve().parents[1] / "work/models")

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        return list(_reranker(self.name, self.cache_dir).rerank(query, texts))


@lru_cache(maxsize=2)
def _reranker(name, cache_dir):
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=name, cache_dir=cache_dir, threads=2)
