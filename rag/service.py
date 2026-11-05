"""Portfolio persistence, ingestion revisions and retrieval behind the Portfolio MCP owner."""

import hashlib
import re
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from agent.handoffs import EvidenceItem
from apps.api.models import EvidenceChunk, PortfolioDocument, VectorCleanup, utcnow
from rag.contracts import DocumentMetadata, DocumentView, EvidenceHit, PortfolioSearch, SearchResult
from rag.ingest.chunkers import chunk_blocks
from rag.ingest.parse import InvalidDocument, parse_document
from rag.retrieval import RetrievalContext
from rag.retriever import get_retriever


class MissingEvidence(LookupError):
    pass


class PortfolioService:
    def __init__(
        self,
        engine,
        embedder,
        vector_index,
        reranker,
        *,
        correction_threshold=0.0,
        max_corrections=2,
    ):
        self.engine, self.embedder = engine, embedder
        self.index, self.reranker = vector_index, reranker
        self.correction_threshold = correction_threshold
        self.max_corrections = max_corrections

    def list_documents(self, tenant):
        with Session(self.engine) as db:
            docs = db.scalars(
                select(PortfolioDocument)
                .where(
                    PortfolioDocument.user_id == tenant,
                )
                .order_by(PortfolioDocument.created_at.desc())
                .limit(500)
            ).all()
            return [DocumentView.model_validate(doc) for doc in docs]

    def ingest(self, tenant: str, filename: str, content: bytes, metadata: DocumentMetadata):
        filename = re.split(r"[/\\]", filename)[-1].strip()
        if not filename or len(filename) > 255:
            raise InvalidDocument("Use a filename of at most 255 characters")
        blocks = list(chunk_blocks(parse_document(filename, content)))
        if len(blocks) > 3000:
            raise InvalidDocument("Too many chunks; split this document into smaller files")
        fingerprint = hashlib.sha256(content).hexdigest()
        details = metadata.model_dump(mode="json")
        with Session(self.engine) as db:
            doc = db.scalar(
                select(PortfolioDocument)
                .where(
                    PortfolioDocument.user_id == tenant,
                    PortfolioDocument.filename == filename,
                )
                .with_for_update()
            )
            if doc and doc.content_hash == fingerprint and doc.details == details:
                if doc.status == "failed":
                    doc.status, doc.error = "queued", None
                    db.commit()
                return DocumentView.model_validate(doc)
            if doc is None:
                doc = PortfolioDocument(
                    id=str(uuid4()),
                    user_id=tenant,
                    filename=filename,
                    content_hash=fingerprint,
                    details=details,
                    revision=1,
                )
                db.add(doc)
            else:
                doc.revision += 1
                doc.content_hash, doc.details = fingerprint, details
                db.execute(
                    delete(EvidenceChunk).where(
                        EvidenceChunk.user_id == tenant,
                        EvidenceChunk.document_id == doc.id,
                    )
                )
            doc.status, doc.error, doc.indexed_model = "queued", None, None
            doc.updated_at = utcnow()
            db.flush()
            for ordinal, block in enumerate(blocks):
                id = str(uuid5(NAMESPACE_URL, f"{tenant}:{doc.id}:{doc.revision}:{ordinal}"))
                db.add(
                    EvidenceChunk(
                        id=id,
                        user_id=tenant,
                        document_id=doc.id,
                        revision=doc.revision,
                        ordinal=ordinal,
                        text=block.text,
                        page=block.page,
                    )
                )
            db.commit()
            return DocumentView.model_validate(doc)

    def index_document(self, tenant, id):
        with Session(self.engine) as db:
            doc = self._document(db, tenant, id)
            if doc.status == "ready" and doc.indexed_model == self.embedder.name:
                return
            doc.status, doc.updated_at = "indexing", utcnow()
            db.commit()
            revision = doc.revision
            rows = self._chunks(db, tenant, id)
            # Detached snapshots keep model loading outside database transactions/locks.
            texts = [row.text for row in rows]
            db.expunge_all()
        vectors = self.embedder.embed(texts)
        with Session(self.engine) as db:
            current = db.scalar(
                select(PortfolioDocument)
                .where(
                    PortfolioDocument.user_id == tenant,
                    PortfolioDocument.id == id,
                )
                .with_for_update()
            )
            if current is None or current.revision != revision:
                return  # A newer upload or deletion wins over an old queued job.
            self.index.replace(tenant, id, rows, vectors)
            current.status, current.error = "ready", None
            current.indexed_model, current.updated_at = self.embedder.name, utcnow()
            db.commit()

    def set_index_error(self, tenant, id, *, retrying=False):
        with Session(self.engine) as db:
            doc = db.scalar(
                select(PortfolioDocument).where(
                    PortfolioDocument.user_id == tenant,
                    PortfolioDocument.id == id,
                )
            )
            if doc and doc.status != "ready":
                doc.status = "queued" if retrying else "failed"
                doc.error = (
                    "Indexing unavailable. Check the worker, embedding model and vector store."
                )
                db.commit()

    def retry(self, tenant, id):
        with Session(self.engine) as db:
            doc = self._document(db, tenant, id)
            doc.status, doc.error = "queued", None
            db.commit()
            return DocumentView.model_validate(doc)

    def delete_document(self, tenant, id):
        with Session(self.engine) as db:
            doc = self._document(db, tenant, id)
            # Remove source text now; vector deletion is a durable, retryable outbox operation.
            db.add(VectorCleanup(document_id=id, user_id=tenant))
            db.delete(doc)
            db.commit()

    def cleanup_vectors(self, tenant, id):
        self.index.remove(tenant, id)
        with Session(self.engine) as db:
            db.execute(
                delete(VectorCleanup).where(
                    VectorCleanup.user_id == tenant,
                    VectorCleanup.document_id == id,
                )
            )
            db.commit()

    def evidence(self, tenant, id) -> EvidenceItem:
        with Session(self.engine) as db:
            row = db.execute(
                select(EvidenceChunk, PortfolioDocument)
                .join(PortfolioDocument)
                .where(
                    EvidenceChunk.user_id == tenant,
                    PortfolioDocument.user_id == tenant,
                    EvidenceChunk.id == id,
                    PortfolioDocument.status == "ready",
                    EvidenceChunk.revision == PortfolioDocument.revision,
                )
            ).first()
            if not row:
                raise MissingEvidence("Evidence not found or no longer indexed")
            return self._item(*row)

    def case_study(self, tenant, id):
        with Session(self.engine) as db:
            doc = self._document(db, tenant, id)
            rows = self._chunks(db, tenant, id)
            if doc.status != "ready":
                raise MissingEvidence("Document is not indexed yet")
            item = self._item(rows[0], doc)
            return item.model_copy(
                update={"id": doc.id, "text": "\n\n".join(row.text for row in rows), "page": None}
            )

    def skills(self, tenant):
        with Session(self.engine) as db:
            docs = db.scalars(
                select(PortfolioDocument).where(
                    PortfolioDocument.user_id == tenant,
                    PortfolioDocument.status == "ready",
                )
            )
            return sorted({skill for doc in docs for skill in doc.details.get("skills", [])})

    def search(self, tenant, request: PortfolioSearch):
        with Session(self.engine) as db:
            rows = db.execute(
                select(EvidenceChunk, PortfolioDocument)
                .join(PortfolioDocument)
                .where(
                    EvidenceChunk.user_id == tenant,
                    PortfolioDocument.user_id == tenant,
                    PortfolioDocument.status == "ready",
                    EvidenceChunk.revision == PortfolioDocument.revision,
                    PortfolioDocument.indexed_model == self.embedder.name,
                )
            ).all()
            allowed = {"persona", "type", "project", "client_industry", "outcome", "skills"}
            if set(request.filters) - allowed:
                raise ValueError("Unsupported evidence filter")
            selected = {}
            for chunk, doc in rows:
                matches = all(
                    (value.casefold() in [s.casefold() for s in doc.details.get("skills", [])])
                    if key == "skills"
                    else str(doc.details.get(key, "")).casefold() == value.casefold()
                    for key, value in request.filters.items()
                )
                if matches:
                    selected[chunk.id] = self._item(chunk, doc)
        texts = {id: item.text for id, item in selected.items()}
        context = RetrievalContext(
            correction_threshold=self.correction_threshold,
            max_corrections=self.max_corrections,
            texts=texts,
            dense=lambda query, k: (
                self.index.search(
                    tenant,
                    self.embedder.query(query),
                    list(texts),
                    min(k, len(texts)),
                )
                if texts
                else []
            ),
            rerank=self.reranker.score,
        )
        ranking = get_retriever(request.variant)(request.query, context=context, k=request.k)
        hits = []
        for id, score in ranking:
            try:
                # Recheck so replaced/deleted evidence cannot escape a stale retrieval snapshot.
                hits.append(EvidenceHit(evidence=self.evidence(tenant, id), score=score))
            except MissingEvidence:
                continue
        return SearchResult(
            variant=request.variant, items=hits, queries=context.queries, abstained=not hits
        )

    @staticmethod
    def _document(db, tenant, id):
        doc = db.scalar(
            select(PortfolioDocument).where(
                PortfolioDocument.user_id == tenant,
                PortfolioDocument.id == id,
            )
        )
        if doc is None:
            raise MissingEvidence("Portfolio document not found")
        return doc

    @staticmethod
    def _chunks(db, tenant, id):
        return list(
            db.scalars(
                select(EvidenceChunk)
                .where(
                    EvidenceChunk.user_id == tenant,
                    EvidenceChunk.document_id == id,
                )
                .order_by(EvidenceChunk.ordinal)
            )
        )

    @staticmethod
    def _item(chunk, doc):
        details = doc.details
        return EvidenceItem(
            id=chunk.id,
            text=chunk.text,
            source=doc.filename,
            type=details["type"],
            date=details.get("date"),
            outcome=details.get("outcome"),
            project=details["project"],
            skills=details.get("skills", []),
            persona=details["persona"],
            client_industry=details.get("client_industry"),
            document_id=doc.id,
            page=chunk.page,
        )
