from typing import Optional, Annotated, List, Any, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session
from uuid import uuid4

from ..clients import get_openai
from ..models import ChatMessage
from ..database import   get_db

router = APIRouter(
prefix="/chat", tags=["chat"]
)


TUTOR_SYSTEM = (
    "You are Invayl Tutor — a patient expert in Python, ML, and DL. "
    "Be concise, show runnable examples, and end with a short follow-up question."
)

class ChatBody(BaseModel):
    message: str
    session_id: Optional[str] = None
    max_output_tokens: Optional[int] = 300


def save_message(db: Session, *, role: str, content: str, session_id: Optional[str]) -> ChatMessage:
    msg = ChatMessage(role=role, content=content, session_id=session_id)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

chat_db = Annotated[Session , Depends(get_db)]



@router.get("/qa")
def list_qa_pairs(
    session_id: Optional[str] = Query(default=None, max_length=64, description="Filter by session/thread id"),
    pair_limit: int = Query(default=50, ge=1, le=500),
    pair_offset: int = Query(default=0, ge=0),
    db: chat_db = None,
):
    """
    GET /chat/all
    Returns Q/A pairs: [{"question": "...", "answer": "...", ...}, ...]
    - If session_id omitted: mixes all sessions, but each pair is from the same session
    - Pagination is by pairs (pair_limit/pair_offset)
    """
    # 1) Fetch messages ordered oldest->newest (stable pairing)
    q = db.query(ChatMessage)
    if session_id:
        q = q.filter(ChatMessage.session_id == session_id)

    msgs: List[ChatMessage] = q.order_by(
        asc(ChatMessage.session_id),   # keep sessions grouped (safe even if None)
        asc(ChatMessage.created_at),
        asc(ChatMessage.id),
    ).all()

    # 2) Pairing: user message -> next assistant message (within same session)
    pairs: List[Dict[str, Any]] = []
    i = 0
    n = len(msgs)

    while i < n:
        m = msgs[i]
        if m.role != "user":
            i += 1
            continue

        # look ahead for the next assistant message in the same session
        j = i + 1
        answer_msg = None
        while j < n:
            nxt = msgs[j]
            # stop scanning if session changes (or there’s another user msg before assistant)
            if nxt.session_id != m.session_id:
                break
            if nxt.role == "assistant":
                answer_msg = nxt
                break
            # if it's another user before assistant, we treat the current user as unanswered
            if nxt.role == "user":
                break
            j += 1

        pair = {
            "session_id": m.session_id,
            "question": m.content,
            "question_id": m.id,
            "question_at": m.created_at,
            "answer": answer_msg.content if answer_msg else None,
            "answer_id": answer_msg.id if answer_msg else None,
            "answer_at": answer_msg.created_at if answer_msg else None,
        }
        pairs.append(pair)
        i += 1 if answer_msg is None else (j + 1 - i)  # jump past the answer if found

    # 3) Pagination over pairs
    total = len(pairs)
    start = pair_offset
    end = pair_offset + pair_limit
    items = pairs[start:end]

    return {
        "total": total,
        "pair_limit": pair_limit,
        "pair_offset": pair_offset,
        "items": items,
    }


@router.get("/all")
def list_chats(
    session_id: Optional[str] = Query(default=None, max_length=64, description="Filter by session/thread id"),
    role: Optional[str] = Query(default=None, description='Filter by role: "user" or "assistant"'),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: chat_db = None,
):
    """
    GET /chat/chats
    - Returns chat messages (optionally filtered by session_id and/or role)
    - Supports pagination via limit/offset
    - Ordered newest first
    """
    q = db.query(ChatMessage)
    if session_id:
        q = q.filter(ChatMessage.session_id == session_id)
    if role in ("user", "assistant"):
        q = q.filter(ChatMessage.role == role)

    total = q.count()
    items: List[ChatMessage] = (
        q.order_by(desc(ChatMessage.created_at), desc(ChatMessage.id))
         .offset(offset)
         .limit(limit)
         .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,  # FastAPI will serialize ORM objects
    }




@router.post("/")
def chat(body: ChatBody, db: chat_db):
    try:
        # 1) Save user message
        save_message(db, role="user", content=body.message, session_id=body.session_id)

        # 2) Call OpenAI
        client = get_openai()
        req = {
            "model": "gpt-4o-mini",
            "input": [
                {"role": "system", "content": TUTOR_SYSTEM},
                {"role": "user", "content": body.message},
            ],
        }
        if body.max_output_tokens is not None:
            req["max_output_tokens"] = body.max_output_tokens

        resp = client.responses.create(**req)

        # 3) Extract reply robustly
        reply = getattr(resp, "output_text", "") or ""
        if not reply and hasattr(resp, "output"):
            parts: List[str] = []
            for item in resp.output:
                if getattr(item, "type", "") == "message":
                    for c in getattr(item, "content", []):
                        if getattr(c, "type", "") == "output_text":
                            parts.append(getattr(c, "text", ""))
            reply = "".join(parts)

        if not reply:
            # If still no reply, fail fast
            raise RuntimeError("No text returned by model")

        # 4) SAVE assistant message (✅ now outside the if, so it runs)
        save_message(db, role="assistant", content=reply, session_id=body.session_id)

        # 5) Return reply (include session_id so the frontend can reuse it)
        return {"reply": reply, "session_id": body.session_id, "usage": getattr(resp, "usage", None)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
def chat_history(
    session_id: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    db: chat_db = None
):
    """
    GET /chat/history?session_id=abc
    - If session_id omitted, returns recent global history.
    """
    q = db.query(ChatMessage)
    if session_id:
        q = q.filter(ChatMessage.session_id == session_id)
    msgs = q.order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).limit(limit).all()
    # return raw objects (FastAPI will serialize)
    return {"session_id": session_id, "messages": msgs}

