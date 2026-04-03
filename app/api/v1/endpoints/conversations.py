import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.conversation import Conversation, ConversationMessage, MessageRole
from app.schemas.conversation import ConversationCreate, ConversationOut, MessageCreate, MessageOut
from app.services.reasoning.orchestrator import LegalReasoningOrchestrator

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    conversation = Conversation(
        organization_id=org.id,
        user_id=user.id,
        matter_id=request.matter_id,
        title=request.title,
        mode=request.mode,
        context={"document_ids": [str(d) for d in request.document_ids]} if request.document_ids else None,
    )
    db.add(conversation)
    await db.flush()
    return conversation


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
    matter_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = [
        Conversation.organization_id == org.id,
        Conversation.user_id == user.id,
        Conversation.is_active == True,  # noqa: E712
    ]
    if matter_id:
        conditions.append(Conversation.matter_id == matter_id)

    stmt = (
        select(Conversation)
        .where(*conditions)
        .order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.organization_id != org.id or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.organization_id != org.id or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.sequence_number.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{conversation_id}/messages", response_model=MessageOut)
async def send_message(
    conversation_id: uuid.UUID,
    request: MessageCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.organization_id != org.id or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Get document context from conversation
    document_ids = None
    if conv.context and conv.context.get("document_ids"):
        document_ids = [uuid.UUID(d) for d in conv.context["document_ids"]]

    # Use the reasoning orchestrator
    orchestrator = LegalReasoningOrchestrator(db)
    result = await orchestrator.answer_question(
        question=request.content,
        organization_id=org.id,
        user_id=user.id,
        document_ids=document_ids,
        matter_id=conv.matter_id,
        conversation_id=conversation_id,
    )

    # Get the assistant message that was created
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == MessageRole.ASSISTANT,
        )
        .order_by(ConversationMessage.sequence_number.desc())
        .limit(1)
    )
    msg_result = await db.execute(stmt)
    assistant_msg = msg_result.scalar_one_or_none()

    if not assistant_msg:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate response")

    return assistant_msg


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.organization_id != org.id or conv.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conv.is_active = False
    await db.flush()
