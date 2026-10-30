import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from groq import APIConnectionError, APIStatusError

from config import get_settings
from logging_config import configure_logging
from models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationHistory,
    DocumentInfo,
    HealthResponse,
)
from services.knowledge_base import KnowledgeBase
from services.rag import RAGService, new_conversation_id

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    knowledge_base = KnowledgeBase(settings)
    if not knowledge_base.chunk_count:
        try:
            indexed = knowledge_base.index_if_empty()
            logger.info("Indexed local policy documents on startup", extra={"chunks": indexed})
        except ValueError as exc:
            logger.warning("Policy knowledge base is empty", extra={"reason": str(exc)})
    app.state.knowledge_base = knowledge_base
    app.state.rag = RAGService(settings, knowledge_base.retriever)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "HTTP request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    conversation_id = body.conversation_id or new_conversation_id()
    try:
        result = await request.app.state.rag.answer(body.question, conversation_id)
        return ChatResponse(
            answer=result.get("answer", ""),
            confidence=float(result.get("confidence", 0)),
            sources=result.get("sources", []),
            conversation_id=conversation_id,
        )
    except APIStatusError as exc:
        logger.exception("Groq returned an API error")
        if exc.status_code == 401:
            detail = "Groq authentication failed. Verify GROQ_API_KEY in the server environment."
        elif exc.status_code == 404:
            detail = (
                f"Groq does not provide model '{settings.groq_model}' to this account. "
                "Set GROQ_MODEL to a model available in your Groq account."
            )
        elif exc.status_code == 429:
            detail = "Groq rate limit or quota reached. Wait and retry, or check your Groq account limits."
        else:
            detail = f"Groq returned HTTP {exc.status_code}. Check the server log for details."
        raise HTTPException(status_code=502 if exc.status_code != 429 else 503, detail=detail) from exc
    except APIConnectionError as exc:
        logger.exception("Could not connect to Groq")
        raise HTTPException(
            status_code=503,
            detail="Could not connect to Groq. Check network access and retry.",
        ) from exc
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=503,
            detail="Policy retrieval or generation failed. Check the server log for details.",
        ) from exc


@app.get("/conversations/{conversation_id}", response_model=ConversationHistory)
async def conversation_history(conversation_id: str, request: Request) -> ConversationHistory:
    return ConversationHistory(
        conversation_id=conversation_id,
        messages=request.app.state.rag.get_history(conversation_id),
    )


@app.delete("/conversations/{conversation_id}", status_code=204)
async def clear_conversation(conversation_id: str, request: Request) -> None:
    request.app.state.rag.clear_history(conversation_id)


@app.get("/documents", response_model=list[DocumentInfo])
async def documents(request: Request) -> list[DocumentInfo]:
    knowledge_base: KnowledgeBase = request.app.state.knowledge_base
    return [DocumentInfo(**item) for item in knowledge_base.document_list()]


@app.get("/documents/{document_name}/chunks")
async def document_chunks(
    document_name: str,
    request: Request,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="Offset must be non-negative and limit must be between 1 and 100.")
    knowledge_base: KnowledgeBase = request.app.state.knowledge_base
    result = knowledge_base.document_chunks(document_name, offset, limit)
    if result["total_chunks"] == 0:
        raise HTTPException(status_code=404, detail="No indexed chunks found for this document.")
    return result
