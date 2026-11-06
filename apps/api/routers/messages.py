from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from apps.api.auth.dependencies import CurrentUser
from apps.api.schemas.conversations import (
    AddClientMessage,
    ConversationView,
    CreateConversation,
    MessageView,
    ReplyDraftView,
)

router = APIRouter(tags=["messages"])


@router.get("/messages", response_model=list[ConversationView])
def list_messages(user: CurrentUser, request: Request):
    return request.app.state.conversations.conversations(user.id)


@router.post("/messages", response_model=ConversationView, status_code=201)
async def create_conversation(body: CreateConversation, user: CurrentUser, request: Request):
    conversation = await run_in_threadpool(request.app.state.conversations.create, user.id, body)
    await request.app.state.enqueue_run(user.id, conversation.run_id)
    return conversation


@router.get("/messages/{id}", response_model=ConversationView)
def get_conversation(id: str, user: CurrentUser, request: Request):
    return request.app.state.conversations.conversation(user.id, id)


@router.get("/messages/{id}/history", response_model=list[MessageView])
def conversation_messages(id: str, user: CurrentUser, request: Request):
    return request.app.state.conversations.messages(user.id, id)


@router.post("/messages/{id}/history", response_model=ConversationView, status_code=202)
async def add_message(id: str, body: AddClientMessage, user: CurrentUser, request: Request):
    conversation = await run_in_threadpool(
        request.app.state.conversations.add_message, user.id, id, body
    )
    await request.app.state.enqueue_run(user.id, conversation.run_id)
    return conversation


@router.get("/messages/{id}/drafts", response_model=list[ReplyDraftView])
def local_replies(id: str, user: CurrentUser, request: Request):
    return request.app.state.conversations.local_replies(user.id, id)
