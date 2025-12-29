from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import logfire
from db.database import get_db
from db.models import User, Conversation, Message
from schemas import QueryRequest, QueryResponse, Role
from routes.v1.auth.auth import get_current_user
from agents.orchestrator import execute_query
from agents.deps import AgentDeps
from configs.google_auth import AuthService
from configs.qdrant import QdrantService
from configs.config import get_settings
import traceback

logger = logfire.configure()
settings = get_settings()

router = APIRouter(tags=["Playground"])

qdrant_service = QdrantService()


@router.post("/query", response_model=QueryResponse)
async def process_query(
    query_request: QueryRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Process natural language query"""

    try:
        user = get_current_user(request, db)
    except HTTPException:
        logger.warning("[QueryRoute] Unauthenticated query attempt")
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Please connect your Google account to use this service.",
                "requires_auth": True,
            },
        )

    credentials = AuthService.get_credentials_from_user(user)
    if not credentials:
        logger.error(f"[QueryRoute] Invalid credentials for user: {user.email}")
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Your Google session has expired. Please reconnect your account.",
                "requires_auth": True,
            },
        )

    logger.info(f"[QueryRoute] Processing query for user: {user.email}")

    conversation_id = query_request.conversation_id

    if not conversation_id:
        conversation = Conversation(
            id=uuid.uuid4(),
            name=query_request.query[:50],
            user_id=user.id,
            created_at=datetime.utcnow(),
        )
        db.add(conversation)
        db.commit()
        conversation_id = conversation.id

        logger.info(f"[QueryRoute] Created new conversation: {conversation_id}")
    else:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
            .first()
        )

        if not conversation:
            logger.error(f"[QueryRoute] Conversation not found: {conversation_id}")
            raise HTTPException(status_code=404, detail="Conversation not found")

    user_message = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        content={"text": query_request.query},
        role=Role.USER,
        created_at=datetime.utcnow(),
    )
    db.add(user_message)
    db.commit()

    deps = AgentDeps(
        user_email=user.email,
        db_session=db,
        conversation_id=str(conversation_id),
        google_credentials=credentials,
        qdrant_service=qdrant_service,
    )

    try:
        result = await execute_query(query_request.query, deps)

        assistant_message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            content={
                "text": result["response"],
                "actions": result.get("actions_taken", []),
            },
            role=Role.BOT,
            intent=result.get("intent"),
            created_at=datetime.utcnow(),
        )

        db.add(assistant_message)
        conversation.updated_at = datetime.utcnow()
        db.commit()

        logger.info(
            f"[QueryRoute] Query processed successfully for conversation: {conversation_id}"
        )

        return QueryResponse(
            response=result["response"],
            actions_taken=result.get("actions_taken", []),
            intent=result.get("intent"),
            conversation_id=conversation_id,
        )

    except Exception as e:
        logger.error(f"[QueryRoute] Query processing error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error processing query: {str(e)}"
        )


@router.get("/conversations")
async def get_conversations(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 20,
):
    """Get user's conversations"""

    try:
        user = get_current_user(request, db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .all()
    )

    logger.info(
        f"[QueryRoute] Retrieved {len(conversations)} conversations for user: {user.email}"
    )

    return {
        "conversations": [
            {
                "id": str(conv.id),
                "name": conv.name,
                "created_at": conv.created_at.isoformat()
                if conv.created_at
                else None,
                "updated_at": conv.updated_at.isoformat()
                if conv.updated_at
                else None,
            }
            for conv in conversations
        ]
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get messages from a conversation"""

    try:
        user = get_current_user(request, db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    logger.info(
        f"[QueryRoute] Retrieved {len(messages)} messages for conversation: {conversation_id}"
    )

    return {
        "conversation_id": str(conversation_id),
        "messages": [
            {
                "id": str(msg.id),
                "role": msg.role.value,
                "content": msg.content,
                "intent": msg.intent,
                "created_at": msg.created_at.isoformat()
                if msg.created_at
                else None,
            }
            for msg in messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a conversation"""

    try:
        user = get_current_user(request, db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conversation)
    db.commit()

    logger.info(f"[QueryRoute] Deleted conversation: {conversation_id}")

    return {"message": "Conversation deleted successfully"}
