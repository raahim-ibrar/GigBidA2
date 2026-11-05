import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from agent.handoffs import EvidenceItem
from apps.api.auth.dependencies import CurrentUser
from rag.contracts import DocumentMetadata, DocumentView, PortfolioSearch, SearchResult
from rag.ingest.parse import InvalidDocument
from rag.service import MissingEvidence

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/documents", response_model=list[DocumentView])
def list_documents(user: CurrentUser, request: Request):
    return request.app.state.portfolio.list_documents(user.id)


@router.post("/portfolio/documents", response_model=DocumentView, status_code=201)
async def upload_document(
    user: CurrentUser,
    request: Request,
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form()],
):
    try:
        details = DocumentMetadata.model_validate_json(metadata)
    except (ValidationError, json.JSONDecodeError):
        raise HTTPException(422, "Invalid document metadata") from None
    content = await file.read(request.app.state.settings.max_portfolio_upload_bytes + 1)
    await file.close()
    if len(content) > request.app.state.settings.max_portfolio_upload_bytes:
        raise HTTPException(413, "Portfolio files must be at most 10 MB")
    try:
        document = await run_in_threadpool(
            request.app.state.portfolio.ingest, user.id, file.filename or "", content, details
        )
    except InvalidDocument as exc:
        raise HTTPException(422, str(exc)) from None
    except IntegrityError:
        raise HTTPException(409, "This source is being updated. Retry the upload.") from None
    if document.status != "ready":
        queued = await request.app.state.enqueue_portfolio(user.id, document.id, document.revision)
        if not queued:
            document.error = (
                "Worker queue unavailable; the saved upload will be retried automatically."
            )
    return document


@router.post("/portfolio/documents/{id}/retry", response_model=DocumentView)
async def retry_document(id: str, user: CurrentUser, request: Request):
    try:
        document = request.app.state.portfolio.retry(user.id, id)
    except MissingEvidence:
        raise HTTPException(404, "Portfolio document not found") from None
    await request.app.state.enqueue_portfolio(user.id, id, document.revision)
    return document


@router.delete("/portfolio/documents/{id}", status_code=204)
def delete_document(id: str, user: CurrentUser, request: Request):
    try:
        request.app.state.portfolio.delete_document(user.id, id)
    except MissingEvidence:
        raise HTTPException(404, "Portfolio document not found") from None


@router.post("/portfolio/search", response_model=SearchResult)
def search_evidence(body: PortfolioSearch, user: CurrentUser, request: Request):
    try:
        return request.app.state.portfolio.search(user.id, body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        raise HTTPException(
            503, "Retrieval unavailable. Check embeddings and the vector store."
        ) from None


@router.get("/portfolio/evidence/{id}", response_model=EvidenceItem)
def get_evidence(id: str, user: CurrentUser, request: Request):
    try:
        return request.app.state.portfolio.evidence(user.id, id)
    except MissingEvidence:
        raise HTTPException(404, "Evidence not found") from None
