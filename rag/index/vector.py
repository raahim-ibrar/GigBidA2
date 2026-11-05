"""Tenant-filtered Qdrant operations. Payloads contain IDs, not portfolio text."""

import hashlib

from qdrant_client import QdrantClient, models


class VectorIndex:
    def __init__(self, client: QdrantClient, *, model: str, dimensions: int):
        self.client = client
        self.dimensions = dimensions
        self.collection = "portfolio_" + hashlib.sha256(model.encode()).hexdigest()[:12]

    def ensure(self):
        if not self.client.collection_exists(self.collection):
            try:
                self.client.create_collection(
                    self.collection,
                    vectors_config=models.VectorParams(
                        size=self.dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
                self.client.create_payload_index(
                    self.collection, "tenant", models.PayloadSchemaType.KEYWORD
                )
            except Exception:
                # A concurrent uploader may have created the same collection.
                if not self.client.collection_exists(self.collection):
                    raise
        size = self.client.get_collection(self.collection).config.params.vectors.size
        if size != self.dimensions:
            raise ValueError("Vector collection uses a different embedding dimension")

    def replace(self, tenant: str, document: str, chunks, vectors):
        self.ensure()
        self.remove(tenant, document)
        points = [
            models.PointStruct(id=c.id, vector=v, payload={"tenant": tenant, "document": document})
            for c, v in zip(chunks, vectors, strict=True)
        ]
        if points:
            self.client.upsert(self.collection, points, wait=True)

    def remove(self, tenant: str, document: str):
        if self.client.collection_exists(self.collection):
            self.client.delete(
                self.collection,
                models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="tenant", match=models.MatchValue(value=tenant)
                            ),
                            models.FieldCondition(
                                key="document", match=models.MatchValue(value=document)
                            ),
                        ]
                    )
                ),
                wait=True,
            )

    def search(self, tenant: str, vector: list[float], allowed_ids: list[str], k: int):
        if not allowed_ids:
            return []
        if not self.client.collection_exists(self.collection):
            raise RuntimeError("Vector index is missing; re-index portfolio sources")
        points = self.client.query_points(
            self.collection,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(key="tenant", match=models.MatchValue(value=tenant)),
                    models.HasIdCondition(has_id=allowed_ids),
                ]
            ),
            limit=k,
            with_payload=False,
        ).points
        return [(str(point.id), float(point.score)) for point in points]
