"""Основной файл FastAPI приложения"""

import asyncio
import json
import logging
import uuid
import time
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from sqlalchemy import text

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware

# Исключения при закрытом WebSocket (отправка после close клиента)
try:
    from websockets.exceptions import ConnectionClosed
    from websockets.exceptions import ConnectionClosedError as WsConnectionClosedError
except ImportError:
    ConnectionClosed = None
    WsConnectionClosedError = None
try:
    from uvicorn.protocols.utils import ClientDisconnected as UvicornClientDisconnected
except ImportError:
    UvicornClientDisconnected = None
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field, validator
import uvicorn

from app.config import settings
from app.core.langgraph_app import get_fever_routing_graph
from app.core.ai_studio import close_ai_studio_client
from app.core.redis_client import get_rate_limiter
from app.db.session import get_db, get_db_session, init_db
from app.db.repositories import SessionRepository, MessageRepository, RecommendationRepository, FeedbackRepository, FeedbackRepository
from app.utils.logging import setup_logging
from app.utils.metrics import get_metrics, track_api_metrics
from app.services.pdf_service import PDFReportGenerator
from app.services.chat_service import ChatService

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)


# Pydantic модели для API
class SessionCreate(BaseModel):
    doctor_id: Optional[str] = None
    patient_initial_data: Optional[Dict[str, Any]] = None


class SessionResponse(BaseModel):
    session_id: str
    created_at: str
    status: str
    urgency_level: Optional[str] = None


class MessageInput(BaseModel):
    session_id: str
    content: str
    
    @validator('content')
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError('Message content cannot be empty')
        if len(v.strip()) > 10000:  # Увеличенный лимит для бэкенда
            raise ValueError('Message content too long (max 10000 characters)')
        # Базовая проверка на потенциально опасный контент
        dangerous_patterns = ['<script', 'javascript:', 'onload=', 'onerror=', 'onclick=']
        content_lower = v.lower()
        for pattern in dangerous_patterns:
            if pattern in content_lower:
                raise ValueError('Message contains potentially dangerous content')
        return v.strip()
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Session ID cannot be empty')
        return v.strip()


class MessageResponse(BaseModel):
    message_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str
    agent_name: Optional[str] = None


class SpecialistInfo(BaseModel):
    name: str
    reasons: List[str]
    priority: str
    timeframe: str
    purpose: str


class RecommendationResponse(BaseModel):
    session_id: str
    urgency_level: str
    primary_specialist: Optional[SpecialistInfo]
    additional_specialists: List[SpecialistInfo]
    required_tests: List[str]
    red_flags: List[str]
    recommendations_text: Optional[str]
    pdf_url: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageResponse]
    created_at: str
    updated_at: str
    status: str


class SessionListItem(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    status: str
    urgency_level: Optional[str] = None
    patient_age_years: Optional[int] = None
    patient_age_months: Optional[int] = None
    message_count: int = 0
    recommendations_count: int = 0


class SessionsListResponse(BaseModel):
    sessions: List[SessionListItem]
    total: int
    limit: int
    offset: int
    created_at: str
    updated_at: str
    status: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: str
    request_id: Optional[str] = None


class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    reset_time: int


# Глобальные переменные
graph_instance = None
pdf_generator = None
chat_service = None
rate_limiter = None

# Константы для rate limiting
MAX_MESSAGES_PER_MINUTE = 30
MAX_MESSAGES_PER_SESSION = 1000
RATE_LIMIT_WINDOW = 60  # секунд


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("Starting Fever Routing System...")
    
    try:
        # Инициализация базы данных
        await init_db()
        logger.info("Database initialized")
        
        # Инициализация графа
        global graph_instance
        graph_instance = await get_fever_routing_graph()
        logger.info("LangGraph initialized")
        
        # Инициализация PDF генератора
        global pdf_generator
        pdf_generator = PDFReportGenerator(settings.pdf_export_dir)
        logger.info("PDF generator initialized")
        
        # Инициализация чат сервиса
        global chat_service
        chat_service = ChatService()
        await chat_service.initialize()
        logger.info("Chat service initialized")
        
        # Инициализация rate limiter
        global rate_limiter
        try:
            rate_limiter = await get_rate_limiter()
            logger.info("Rate limiter initialized")
            
            # Запускаем периодическую очистку старых записей
            import asyncio
            asyncio.create_task(periodic_rate_limit_cleanup())
            asyncio.create_task(periodic_websocket_cleanup())
        except Exception as e:
            logger.warning(f"Rate limiter initialization failed: {str(e)}. Using fallback mode.")
            rate_limiter = None
        
        logger.info("Application startup completed")
        
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    try:
        # Закрытие AI Studio клиента
        await close_ai_studio_client()
        logger.info("AI Studio client closed")
        
        logger.info("Application shutdown completed")
        
        # Закрытие rate limiter (rate_limiter уже объявлен global в startup)
        if rate_limiter:
            await rate_limiter.close()
            logger.info("Rate limiter closed")
        
        logger.info("Application shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")


async def periodic_rate_limit_cleanup():
    """Периодическая очистка старых записей rate limiting"""
    import asyncio
    while True:
        try:
            await asyncio.sleep(3600)  # Каждый час
            if rate_limiter:
                await rate_limiter.cleanup_old_entries()
        except Exception as e:
            logger.error(f"Rate limit cleanup error: {str(e)}")


async def periodic_websocket_cleanup():
    """Периодическая очистка неактивных WebSocket соединений"""
    import asyncio
    while True:
        try:
            await asyncio.sleep(300)  # Каждые 5 минут
            await manager.cleanup_inactive_connections()
        except Exception as e:
            logger.error(f"WebSocket cleanup error: {str(e)}")


# Создание FastAPI приложения
app = FastAPI(
    title="Fever Routing System API",
    description="Мультиагентная система для маршрутизации детей с лихорадкой",
    version="1.0.0",
    lifespan=lifespan
)

# GZip middleware для сжатия ответов
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS — последний add_middleware = внешний слой, обрабатывает preflight OPTIONS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Явная обработка preflight OPTIONS — гарантированно возвращаем CORS-заголовки
class CorsPreflightMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method != "OPTIONS":
            return await call_next(request)
        origin = request.headers.get("origin") or ""
        allowed = settings.cors_origins
        if origin and (origin in allowed or "*" in allowed):
            allow_origin = origin
        elif allowed and "*" not in allowed:
            allow_origin = allowed[0]
        else:
            allow_origin = "http://localhost:3000"
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": allow_origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Max-Age": "600",
            },
        )


app.add_middleware(CorsPreflightMiddleware)

# Middleware для отслеживания запросов и ограничения частоты
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Генерируем уникальный ID для запроса (correlation ID)
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Добавляем correlation ID в логи
    logger.info(
        f"Request {request.method} {request.url.path}",
        extra={"request_id": request_id, "method": request.method, "path": request.url.path}
    )
    
    # Получаем session_id из параметров запроса или заголовков
    session_id = None
    if request.method == "POST" and "/api/v1/chat/message" in request.url.path:
        try:
            body = await request.json()
            session_id = body.get("session_id")
        except:
            pass
    
    if not session_id:
        session_id = request.headers.get("X-Session-ID")
    
    # Проверяем лимиты, если есть session_id и rate limiter доступен
    if session_id and rate_limiter:
        try:
            # Проверка лимита сообщений в минуту
            is_allowed, remaining, reset_time = await rate_limiter.check_rate_limit(
                identifier=f"session:{session_id}",
                max_requests=MAX_MESSAGES_PER_MINUTE,
                window_seconds=RATE_LIMIT_WINDOW
            )
            
            if not is_allowed:
                return JSONResponse(
                    status_code=429,
                    content=ErrorResponse(
                        error="Rate limit exceeded",
                        detail=f"Too many messages. Maximum {MAX_MESSAGES_PER_MINUTE} messages per {RATE_LIMIT_WINDOW} seconds.",
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        request_id=request_id
                    ).dict(),
                    headers={
                        "X-RateLimit-Limit": str(MAX_MESSAGES_PER_MINUTE),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time),
                        "X-Request-ID": request_id
                    }
                )
        
            # Проверка общего лимита сообщений для сессии
            session_total_allowed, session_remaining, _ = await rate_limiter.check_rate_limit(
                identifier=f"session_total:{session_id}",
                max_requests=MAX_MESSAGES_PER_SESSION,
                window_seconds=86400  # 24 часа
            )
            
            if not session_total_allowed:
                return JSONResponse(
                    status_code=429,
                    content=ErrorResponse(
                        error="Session limit exceeded",
                        detail=f"Maximum {MAX_MESSAGES_PER_SESSION} messages per session.",
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        request_id=request_id
                    ).dict(),
                    headers={"X-Request-ID": request_id}
                )
        
            # Обрабатываем запрос
            response = await call_next(request)
        
            # Добавляем заголовки с информацией о лимитах
            response.headers["X-RateLimit-Limit"] = str(MAX_MESSAGES_PER_MINUTE)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
            response.headers["X-Request-ID"] = request_id
        
            return response
    
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}", exc_info=True)
            # В случае ошибки Redis продолжаем обработку (fail-open)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
    
    # Если нет session_id или rate limiter недоступен, просто обрабатываем запрос
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _is_connection_closed_exception(e: BaseException, _depth: int = 0) -> bool:
    """Проверка, что исключение связано с закрытым WebSocket (клиент отключился)."""
    if _depth > 6:
        return False
    if isinstance(e, asyncio.CancelledError):
        return True
    if isinstance(e, WebSocketDisconnect):
        return True
    if ConnectionClosed is not None and isinstance(e, ConnectionClosed):
        return True
    if WsConnectionClosedError is not None and isinstance(e, WsConnectionClosedError):
        return True
    if UvicornClientDisconnected is not None and isinstance(e, UvicornClientDisconnected):
        return True
    tname = type(e).__name__
    if tname in ("ClientDisconnected", "ConnectionClosedError"):
        return True
    msg = str(e).lower()
    if any(
        s in msg
        for s in (
            "disconnect",
            "connection closed",
            "going away",
            "close frame",
            "cannot call \"send\"",
            "once a close",
            "client disconnected",
        )
    ):
        return True
    if any(code in msg for code in (" 1000", " 1001", " 1012", "code=1000", "code=1001")):
        return True
    cause = getattr(e, "__cause__", None)
    if cause is not None and cause is not e:
        return _is_connection_closed_exception(cause, _depth + 1)
    return False


async def _safe_ws_send(websocket: WebSocket, message: dict) -> bool:
    """
    Отправка JSON по WebSocket. Возвращает False, если соединение уже закрыто (клиент отключился).
    Не логирует как ERROR нормальное закрытие клиентом.
    """
    try:
        await websocket.send_json(message)
        return True
    except WebSocketDisconnect:
        return False
    except Exception as e:
        if _is_connection_closed_exception(e):
            logger.debug("WebSocket already closed by client, skip send: %s", e)
            return False
        raise


# WebSocket менеджер для чата
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_timestamps: Dict[str, float] = {}
        self.last_activity: Dict[str, float] = {}
        self.connection_timeout = 3600  # 1 час бездействия
        self.max_connection_age = 86400  # 24 часа максимальный возраст соединения
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        current_time = time.time()
        self.active_connections[session_id] = websocket
        self.connection_timestamps[session_id] = current_time
        self.last_activity[session_id] = current_time
        logger.info(f"WebSocket connected for session {session_id}")
    
    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            if session_id in self.connection_timestamps:
                del self.connection_timestamps[session_id]
            if session_id in self.last_activity:
                del self.last_activity[session_id]
            logger.info(f"WebSocket disconnected for session {session_id}")
    
    def update_activity(self, session_id: str):
        """Обновление времени последней активности"""
        if session_id in self.last_activity:
            self.last_activity[session_id] = time.time()
    
    async def send_message(self, session_id: str, message: dict):
        if session_id not in self.active_connections:
            return
        websocket = self.active_connections[session_id]
        try:
            await websocket.send_json(message)
            self.update_activity(session_id)
        except WebSocketDisconnect:
            self.disconnect(session_id)
        except Exception as e:
            if _is_connection_closed_exception(e):
                logger.debug("WebSocket closed by client, skip send for session %s: %s", session_id, e)
                self.disconnect(session_id)
            else:
                logger.error("Error sending WebSocket message for session %s: %s", session_id, e)
                self.disconnect(session_id)
    
    async def cleanup_inactive_connections(self):
        """Очистка неактивных соединений"""
        current_time = time.time()
        inactive_sessions = []
        
        for session_id, last_activity_time in list(self.last_activity.items()):
            connection_age = current_time - self.connection_timestamps.get(session_id, current_time)
            inactivity_time = current_time - last_activity_time
            
            # Закрываем соединения, которые неактивны слишком долго или слишком старые
            if inactivity_time > self.connection_timeout or connection_age > self.max_connection_age:
                inactive_sessions.append(session_id)
        
        for session_id in inactive_sessions:
            logger.info(f"Closing inactive WebSocket connection for session {session_id}")
            try:
                websocket = self.active_connections.get(session_id)
                if websocket:
                    await websocket.close(code=1008, reason="Connection timeout")
            except Exception as e:
                logger.error(f"Error closing inactive connection: {str(e)}")
            finally:
                self.disconnect(session_id)


manager = ConnectionManager()


# API Endpoints

@app.post("/api/v1/sessions", response_model=SessionResponse)
@track_api_metrics("POST", "/api/v1/sessions")
async def create_session(session_data: SessionCreate):
    """Создание новой сессии диалога"""
    try:
        session_id = str(uuid.uuid4())
        
        # Создание сессии в графе
        await graph_instance.create_session(session_id, session_data.doctor_id)
        
        # Сохранение в базу данных
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.create_session(
                session_id=session_id,
                doctor_id=session_data.doctor_id,
                patient_age_years=session_data.patient_initial_data.get("age_years") if session_data.patient_initial_data else None,
                patient_age_months=session_data.patient_initial_data.get("age_months") if session_data.patient_initial_data else None
            )
        
        logger.info(f"Created new session {session_id}")
        
        return SessionResponse(
            session_id=session_id,
            created_at=session.created_at.isoformat(),
            status="active"
        )
        
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create session")


@app.get("/api/v1/sessions/{session_id}")
@track_api_metrics("GET", "/api/v1/sessions/{session_id}")
async def get_session(session_id: str):
    """Получение информации о сессии"""
    try:
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_session(session_id)
            
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return {
                "session_id": session.id,
                "doctor_id": session.doctor_id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "status": session.status,
                "urgency_level": session.urgency_level,
                "patient_age_years": session.patient_age_years,
                "patient_age_months": session.patient_age_months
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get session")


@app.post("/api/v1/chat/message", response_model=MessageResponse)
@track_api_metrics("POST", "/api/v1/chat/message")
async def send_message(message_data: MessageInput, request: Request):
    """Отправка сообщения в чат"""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    try:
        # Дополнительная валидация на бэкенде
        if not message_data.session_id or not message_data.content:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="Validation error",
                    detail="Session ID and content are required",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    request_id=request_id
                ).dict()
            )
        
        # Проверка существования сессии
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_session(message_data.session_id)
            
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail=ErrorResponse(
                        error="Session not found",
                        detail=f"Session {message_data.session_id} does not exist",
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        request_id=request_id
                    ).dict()
                )
        
        # Обработка сообщения через граф
        try:
            result = await graph_instance.process_message(
                session_id=message_data.session_id,
                message=message_data.content
            )
        except Exception as graph_error:
            logger.error(f"Graph processing error for session {message_data.session_id}: {str(graph_error)}")
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    error="Processing error",
                    detail="Failed to process message with AI service",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    request_id=request_id
                ).dict()
            )
        
        if not result["success"]:
            resp_fallback = (result.get("response") or "").strip()
            if not resp_fallback:
                raise HTTPException(
                    status_code=500,
                    detail=ErrorResponse(
                        error="Processing failed",
                        detail=result.get("error", "Unknown processing error"),
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        request_id=request_id
                    ).dict()
                )
            logger.warning(
                "Graph success=False but response present for session %s; returning assistant text (HTTP)",
                message_data.session_id,
            )
            result = {**result, "response": resp_fallback}
        
        # Сохранение сообщений в базу данных
        try:
            async with get_db_session() as db:
                message_repo = MessageRepository(db)
                
                # Сохранение сообщения пользователя
                user_message = await message_repo.create_message(
                    session_id=message_data.session_id,
                    role="user",
                    content=message_data.content
                )
                
                # Сохранение ответа ассистента
                assistant_message = None
                if result["response"]:
                    assistant_message = await message_repo.create_message(
                        session_id=message_data.session_id,
                        role="assistant",
                        content=result["response"],
                        agent_name=result.get("current_step")
                    )
        except Exception as db_error:
            logger.error(f"Database error for session {message_data.session_id}: {str(db_error)}")
            # Продолжаем обработку даже если сохранение в БД не удалось
        
        # Отправка через WebSocket если есть активное соединение
        try:
            await manager.send_message(message_data.session_id, {
                "type": "message",
                "message": {
                    "message_id": str(assistant_message.id) if assistant_message else "temp",
                    "role": "assistant",
                    "content": result["response"] or "No response",
                    "timestamp": assistant_message.created_at.isoformat() if assistant_message else "",
                    "agent_name": result.get("current_step")
                }
            })
            
            # Отправка статуса
            await manager.send_message(message_data.session_id, {
                "type": "status",
                "current_step": result.get("current_step"),
                "urgency_level": result.get("urgency_level"),
                "needs_more_info": result.get("needs_more_info", False),
                "questions_to_ask": result.get("questions_to_ask", [])
            })
        except Exception as ws_error:
            if _is_connection_closed_exception(ws_error):
                logger.debug("WebSocket already closed for session %s (client left)", message_data.session_id)
            else:
                logger.error("WebSocket error for session %s: %s", message_data.session_id, ws_error)
            # Продолжаем обработку даже если отправка через WebSocket не удалась
        
        return MessageResponse(
            message_id=str(assistant_message.id) if assistant_message else "temp",
            role="assistant",
            content=result["response"] or "No response",
            timestamp=assistant_message.created_at.isoformat() if assistant_message else "",
            agent_name=result.get("current_step")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="Internal server error",
                detail="An unexpected error occurred while processing your request",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                request_id=request_id
            ).dict()
        )


@app.websocket("/api/v1/chat/stream/{session_id}")
async def chat_stream(websocket: WebSocket, session_id: str):
    """WebSocket для стриминга ответов агентов"""
    try:
        uuid.UUID(session_id)
    except ValueError:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "message": "Некорректный session_id: ожидается UUID (например из POST /api/v1/sessions).",
            }
        )
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, session_id)
    logger.info(f"WebSocket connection established for session {session_id}")
    
    # Проверяем и инициализируем сессию в chat_service при подключении
    try:
        # Проверяем, существует ли сессия в базе данных
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_session(session_id)
            
            if not session:
                logger.error(f"Session {session_id} not found in database")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Session {session_id} not found"
                })
                await websocket.close(code=1008, reason="Session not found")
                return
        
        # Проверяем, существует ли сессия в графе
        session_state = await graph_instance.get_session_state(session_id)
        if not session_state:
            # Создаем сессию в графе, если она не существует
            logger.info(f"Creating session {session_id} in graph")
            await graph_instance.create_session(session_id, session.doctor_id)
        
        # Регистрируем сессию в chat_service, если она еще не зарегистрирована
        if session_id not in chat_service.active_sessions:
            logger.info(f"Registering session {session_id} in chat_service")
            chat_service.active_sessions[session_id] = {
                "created_at": session.created_at,
                "doctor_id": session.doctor_id,
                "message_count": 0,
                "last_activity": session.updated_at
            }
        
        # Отправляем подтверждение подключения
        await websocket.send_json({
            "type": "connection_established",
            "session_id": session_id,
            "status": "connected"
        })
        
    except Exception as e:
        logger.error(f"Error initializing session {session_id}: {str(e)}")
        await websocket.send_json({
            "type": "error",
            "message": f"Failed to initialize session: {str(e)}"
        })
        await websocket.close(code=1011, reason="Session initialization failed")
        return
    
    try:
        while True:
            # Получение сообщения от клиента с таймаутом
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=300)  # 5 минут таймаут
            except asyncio.TimeoutError:
                logger.info(f"WebSocket timeout for session {session_id}, sending ping")
                if not await _safe_ws_send(websocket, {"type": "ping"}):
                    break
                continue
            except asyncio.CancelledError:
                raise
            except json.JSONDecodeError as je:
                logger.debug("Invalid JSON from WebSocket client session %s: %s", session_id, je)
                if not await _safe_ws_send(
                    websocket, {"type": "error", "message": "Некорректный JSON в сообщении"}
                ):
                    break
                continue
            except WebSocketDisconnect:
                break
            except Exception as recv_err:
                if _is_connection_closed_exception(recv_err):
                    logger.debug("WebSocket receive closed for session %s: %s", session_id, recv_err)
                    break
                # Starlette может кинуть ValueError при невалидном JSON
                if isinstance(recv_err, ValueError) and (
                    "json" in str(recv_err).lower() or "expecting value" in str(recv_err).lower()
                ):
                    logger.debug("Invalid message body for session %s: %s", session_id, recv_err)
                    if not await _safe_ws_send(
                        websocket, {"type": "error", "message": "Некорректный JSON в сообщении"}
                    ):
                        break
                    continue
                raise
            
            logger.debug(f"Received WebSocket message for session {session_id}: {data}")
            
            # Валидация формата сообщения
            if not isinstance(data, dict) or "type" not in data:
                if not await _safe_ws_send(websocket, {"type": "error", "message": "Invalid message format"}):
                    break
                continue
            
            if data.get("type") == "ping":
                manager.update_activity(session_id)
                if not await _safe_ws_send(websocket, {"type": "pong", "timestamp": time.time()}):
                    break
                continue
            
            if data.get("type") == "message":
                # Валидация сообщения
                content = data.get("content", "")
                if not content or not isinstance(content, str):
                    if not await _safe_ws_send(websocket, {"type": "error", "message": "Message content is required and must be a string"}):
                        break
                    continue
                
                if len(content) > 10000:
                    if not await _safe_ws_send(websocket, {"type": "error", "message": "Message content too long (max 10000 characters)"}):
                        break
                    continue
                
                # Проверяем существование сессии перед обработкой
                if session_id not in chat_service.active_sessions:
                    logger.error(f"Session {session_id} not found in active sessions")
                    if not await _safe_ws_send(websocket, {"type": "error", "message": "Session not found in active sessions"}):
                        break
                    continue
                
                # Проверка лимитов для WebSocket (используем Redis если доступен)
                if rate_limiter:
                    try:
                        is_allowed, remaining, reset_time = await rate_limiter.check_rate_limit(
                            identifier=f"session:{session_id}",
                            max_requests=MAX_MESSAGES_PER_MINUTE,
                            window_seconds=RATE_LIMIT_WINDOW
                        )
                        
                        if not is_allowed:
                            if not await _safe_ws_send(websocket, {
                                "type": "error",
                                "message": f"Rate limit exceeded: {MAX_MESSAGES_PER_MINUTE} messages per {RATE_LIMIT_WINDOW} seconds",
                                "reset_time": reset_time
                            }):
                                break
                            continue
                    except Exception as e:
                        logger.error(f"WebSocket rate limiting error: {str(e)}")
                        # Продолжаем обработку при ошибке Redis
                
                # Обновляем активность
                manager.update_activity(session_id)
                
                # Отправляем немедленное подтверждение получения сообщения
                message_id = data.get("id", f"msg_{int(time.time() * 1000)}_{session_id[:8]}")
                if not await _safe_ws_send(websocket, {"type": "message_received", "message_id": message_id, "timestamp": time.time()}):
                    break
                
                # Обработка сообщения через chat_service (долгая операция — клиент может успеть закрыть сокет)
                async def on_agent_progress(agent_key: str, title: str, description: str) -> None:
                    await _safe_ws_send(websocket, {
                        "type": "agent_progress",
                        "agent_key": agent_key,
                        "title": title,
                        "description": description,
                        "status": "completed",
                    })

                try:
                    logger.info("WebSocket: calling send_message with progress_callback (astream path)")
                    result = await chat_service.send_message(
                        session_id=session_id,
                        message=content,
                        progress_callback=on_agent_progress,
                    )
                    
                    logger.info(f"Message processed successfully for session {session_id}")
                    
                    # Отправка результата (если клиент уже отключился — не логируем как ошибку)
                    if not await _safe_ws_send(websocket, {"type": "response", "data": result}):
                        break
                    if not await _safe_ws_send(websocket, {
                        "type": "status",
                        "current_step": result.get("current_step"),
                        "urgency_level": result.get("urgency_level"),
                        "needs_more_info": result.get("needs_more_info", False),
                        "questions_to_ask": result.get("questions_to_ask", [])
                    }):
                        break
                    
                except Exception as e:
                    if _is_connection_closed_exception(e):
                        logger.debug("Client disconnected during processing: %s", e)
                        break
                    logger.error("Error processing message in WebSocket: %s", e, exc_info=True)
                    detail = str(e).strip()[:800] or None
                    err_payload: dict = {
                        "type": "error",
                        "message": "Failed to process message. Please try again.",
                    }
                    if detail:
                        err_payload["detail"] = detail
                    await _safe_ws_send(websocket, err_payload)
            
            elif data.get("type") == "command":
                # Валидация команды
                command = data.get("command")
                if not command or not isinstance(command, str):
                    if not await _safe_ws_send(websocket, {"type": "error", "message": "Command is required and must be a string"}):
                        break
                    continue
                
                # Обработка команд (start, pause и т.д.)
                logger.info(f"Received command: {command} for session {session_id}")
                
                # Временно отправляем подтверждение получения команды
                if not await _safe_ws_send(websocket, {"type": "command_response", "command": command, "status": "received"}):
                    break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        if _is_connection_closed_exception(e):
            logger.debug("WebSocket closed by client for session %s: %s", session_id, e)
        else:
            logger.error("WebSocket error for session %s: %s", session_id, e)
    finally:
        manager.disconnect(session_id)


@app.get("/api/v1/sessions/{session_id}/recommendations")
@track_api_metrics("GET", "/api/v1/sessions/{session_id}/recommendations")
async def get_recommendations(session_id: str):
    """Получение финальных рекомендаций"""
    try:
        # Получение состояния графа
        state = await graph_instance.get_session_state(session_id)
        
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Проверка наличия рекомендаций
        if not state.get("synthesis_output"):
            raise HTTPException(status_code=404, detail="Recommendations not available")
        
        recommendations = state.get("recommendations", {})
        
        # Преобразование SpecialistInfo
        primary_specialist = None
        if recommendations.get("primary_specialist"):
            primary_data = recommendations["primary_specialist"]
            primary_specialist = SpecialistInfo(**primary_data)
        
        additional_specialists = []
        for spec_data in recommendations.get("additional_specialists", []):
            additional_specialists.append(SpecialistInfo(**spec_data))
        
        return RecommendationResponse(
            session_id=session_id,
            urgency_level=state.get("urgency_level", "routine"),
            primary_specialist=primary_specialist,
            additional_specialists=additional_specialists,
            required_tests=recommendations.get("required_tests", []),
            red_flags=recommendations.get("red_flags", []),
            recommendations_text=recommendations.get("recommendations_text")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recommendations for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get recommendations")


@app.post("/api/v1/export/pdf/{session_id}")
@track_api_metrics("POST", "/api/v1/export/pdf/{session_id}")
async def export_to_pdf(session_id: str, background_tasks: BackgroundTasks):
    """Экспорт рекомендаций в PDF"""
    try:
        # Получение состояния графа
        state = await graph_instance.get_session_state(session_id)
        
        if not state:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Проверка существования сессии
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
        
        # Снимок данных графа для фоновой задачи (чтобы не зависеть от жизни state)
        snapshot = {
            "patient_data": dict(state.get("patient_data") or {}),
            "recommendations": dict(state.get("recommendations") or {}),
        }
        
        async def generate_pdf():
            try:
                async with get_db_session() as db:
                    session_repo = SessionRepository(db)
                    message_repo = MessageRepository(db)
                    recommendation_repo = RecommendationRepository(db)
                    session = await session_repo.get_session(session_id)
                    messages = await message_repo.get_session_messages(session_id)
                    recommendation = await recommendation_repo.get_session_recommendations(session_id)
                    
                    pdf_path = await pdf_generator.generate_report(
                        session_id=session_id,
                        patient_data=snapshot["patient_data"],
                        recommendations=snapshot["recommendations"],
                        session_data=session,
                        messages=messages
                    )
                    
                    if recommendation:
                        await recommendation_repo.update_pdf_path(
                            recommendation_id=recommendation.id,
                            pdf_path=pdf_path
                        )
                
                logger.info(f"PDF generated for session {session_id}: {pdf_path}")
                
            except Exception as e:
                logger.error(f"Error generating PDF for session {session_id}: {str(e)}", exc_info=True)
        
        background_tasks.add_task(generate_pdf)
        
        return {
            "message": "PDF generation started",
            "session_id": session_id,
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting PDF export for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start PDF export")


@app.get("/api/v1/export/pdf/{session_id}/download")
@track_api_metrics("GET", "/api/v1/export/pdf/{session_id}/download")
async def download_pdf(session_id: str):
    """Скачивание PDF файла"""
    try:
        async with get_db_session() as db:
            recommendation_repo = RecommendationRepository(db)
            recommendations = await recommendation_repo.get_session_recommendations(session_id)
            
            if not recommendations or not recommendations.pdf_path:
                raise HTTPException(status_code=404, detail="PDF not found")
            
            return FileResponse(
                path=recommendations.pdf_path,
                filename=f"recommendations_{session_id}.pdf",
                media_type="application/pdf"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading PDF for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download PDF")


@app.get("/api/v1/sessions", response_model=SessionsListResponse)
@track_api_metrics("GET", "/api/v1/sessions")
async def get_sessions_list(limit: int = 50, offset: int = 0):
    """Получение списка всех сессий (история консультаций)"""
    try:
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            message_repo = MessageRepository(db)
            recommendation_repo = RecommendationRepository(db)
            
            # Получаем сессии
            sessions = await session_repo.get_all_sessions(limit=limit, offset=offset)
            total = await session_repo.get_sessions_count()
            
            # Формируем список с дополнительной информацией
            session_items = []
            for session in sessions:
                # Получаем количество сообщений
                messages = await message_repo.get_session_messages(session.id)
                message_count = len(messages)
                
                # Получаем количество рекомендаций
                recommendation = await recommendation_repo.get_session_recommendations(session.id)
                recommendations_count = 1 if recommendation else 0
                
                session_items.append(SessionListItem(
                    session_id=session.id,
                    created_at=session.created_at.isoformat(),
                    updated_at=session.updated_at.isoformat(),
                    status=session.status,
                    urgency_level=session.urgency_level,
                    patient_age_years=session.patient_age_years,
                    patient_age_months=session.patient_age_months,
                    message_count=message_count,
                    recommendations_count=recommendations_count
                ))
            
            return SessionsListResponse(
                sessions=session_items,
                total=total,
                limit=limit,
                offset=offset
            )
            
    except Exception as e:
        logger.error(f"Error getting sessions list: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get sessions list")


@app.get("/api/v1/sessions/{session_id}/history")
@track_api_metrics("GET", "/api/v1/sessions/{session_id}/history")
async def get_chat_history(session_id: str):
    """Получение истории диалога"""
    try:
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_session(session_id)
            
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            message_repo = MessageRepository(db)
            messages = await message_repo.get_session_messages(session_id)
            
            message_responses = []
            for msg in messages:
                message_responses.append(MessageResponse(
                    message_id=str(msg.id),
                    role=msg.role,
                    content=msg.content,
                    timestamp=msg.created_at.isoformat(),
                    agent_name=msg.agent_name
                ))
            
            return ChatHistoryResponse(
                session_id=session_id,
                messages=message_responses,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                status=session.status
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat history for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get chat history")


@app.get("/metrics")
async def metrics():
    """Prometheus метрики"""
    return get_metrics()


@app.get("/health")
@track_api_metrics("GET", "/health")
async def health_check():
    """Health check endpoint с расширенными проверками"""
    components_status = {}
    overall_healthy = True
    
    try:
        # Проверка подключения к базе данных
        try:
            async with get_db_session() as db:
                await db.execute(text("SELECT 1"))
            components_status["database"] = "healthy"
        except Exception as e:
            components_status["database"] = f"unhealthy: {str(e)}"
            overall_healthy = False
        
        # Проверка графа
        try:
            if not graph_instance or not hasattr(graph_instance, '_initialized') or not graph_instance._initialized:
                raise Exception("Graph not initialized")
            components_status["graph"] = "healthy"
        except Exception as e:
            components_status["graph"] = f"unhealthy: {str(e)}"
            overall_healthy = False
        
        # Проверка Redis
        try:
            if rate_limiter:
                await rate_limiter.redis_client.ping()
                components_status["redis"] = "healthy"
            else:
                components_status["redis"] = "not_initialized"
        except Exception as e:
            components_status["redis"] = f"unhealthy: {str(e)}"
            # Redis не критичен для работы, только предупреждение
            logger.warning(f"Redis health check failed: {str(e)}")
        
        # Проверка AI Studio connectivity
        try:
            from app.core.ai_studio import get_ai_studio_client
            ai_client = await get_ai_studio_client()
            if ai_client and ai_client.openai_client:
                # Простая проверка - клиент инициализирован
                components_status["ai_studio"] = "connected"
            else:
                components_status["ai_studio"] = "not_initialized"
        except Exception as e:
            components_status["ai_studio"] = f"error: {str(e)}"
            # AI Studio может быть недоступен временно
            logger.warning(f"AI Studio health check failed: {str(e)}")
        
        # Проверка чат сервиса
        try:
            if chat_service and hasattr(chat_service, 'graph') and chat_service.graph:
                components_status["chat_service"] = "healthy"
            else:
                components_status["chat_service"] = "not_initialized"
        except Exception as e:
            components_status["chat_service"] = f"unhealthy: {str(e)}"
            overall_healthy = False
        
        if overall_healthy:
            return {
                "status": "healthy",
                "timestamp": asyncio.get_event_loop().time(),
                "version": settings.app_version,
                "components": components_status
            }
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "timestamp": asyncio.get_event_loop().time(),
                    "version": settings.app_version,
                    "components": components_status
                }
            )
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time(),
                "components": components_status
            }
        )


# Тестовый endpoint для отладки
@app.post("/api/v1/debug/state")
async def debug_state(message_data: MessageInput):
    """Тестовый endpoint для отладки создания состояния"""
    try:
        from app.core.state import create_initial_state
        from langchain_core.messages import HumanMessage
        
        logger.info(f"Debug: Creating state for session {message_data.session_id}")
        
        # Создание начального состояния
        initial_state = create_initial_state(message_data.session_id)
        
        # Добавление сообщения
        human_message = HumanMessage(content=message_data.content)
        initial_state["messages"] = [human_message]
        
        logger.info(f"Debug: State created successfully")
        logger.debug(f"Debug: State type: {type(initial_state)}")
        logger.debug(f"Debug: State keys: {list(initial_state.keys())}")
        logger.debug(f"Debug: Session ID: {initial_state.get('session_id')}")
        
        return {
            "success": True,
            "state_type": str(type(initial_state)),
            "state_keys": list(initial_state.keys()),
            "session_id": initial_state.get('session_id'),
            "message_count": len(initial_state.get('messages', []))
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Debug error: {str(e)}")
        logger.error(f"Debug traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# Обработчики ошибок
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    
    # Если деталь уже в формате ErrorResponse, просто возвращаем ее
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers={"X-Request-ID": request_id}
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="HTTP Error",
            detail=str(exc.detail),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            request_id=request_id
        ).dict(),
        headers={"X-Request-ID": request_id}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail="An unexpected error occurred while processing your request",
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            request_id=request_id
        ).dict(),
        headers={"X-Request-ID": request_id}
    )


# Endpoint для проверки статуса лимитов
@app.get("/api/v1/rate-limit/status")
async def rate_limit_status(request: Request):
    """Получение информации о текущих лимитах для сессии"""
    session_id = request.headers.get("X-Session-ID")
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    if not session_id:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="Missing session ID",
                detail="X-Session-ID header is required",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                request_id=request_id
            ).dict()
        )
    
    # Используем Redis rate limiter если доступен
    if rate_limiter:
        try:
            status = await rate_limiter.get_rate_limit_status(
                identifier=f"session:{session_id}",
                max_requests=MAX_MESSAGES_PER_MINUTE,
                window_seconds=RATE_LIMIT_WINDOW
            )
            return RateLimitInfo(
                limit=status["limit"],
                remaining=status["remaining"],
                reset_time=status["reset_time"]
            )
        except Exception as e:
            logger.error(f"Rate limit status error: {str(e)}")
            # Fallback на базовую информацию
            return RateLimitInfo(
                limit=MAX_MESSAGES_PER_MINUTE,
                remaining=MAX_MESSAGES_PER_MINUTE,
                reset_time=int(time.time()) + RATE_LIMIT_WINDOW
            )
    else:
        # Fallback если Redis недоступен
        return RateLimitInfo(
            limit=MAX_MESSAGES_PER_MINUTE,
            remaining=MAX_MESSAGES_PER_MINUTE,
            reset_time=int(time.time()) + RATE_LIMIT_WINDOW
        )


# Модели для обратной связи
class FeedbackInput(BaseModel):
    session_id: str
    was_helpful: bool
    helped_decision: bool
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    session_id: str
    was_helpful: bool
    helped_decision: bool
    rating: Optional[int] = None
    comment: Optional[str] = None
    created_at: str
    message: str


@app.post("/api/v1/feedback", response_model=FeedbackResponse)
@track_api_metrics("POST", "/api/v1/feedback")
async def submit_feedback(feedback_data: FeedbackInput, request: Request):
    """Сохранение обратной связи от пользователя"""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    
    try:
        # Валидация session_id
        async with get_db_session() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_session(feedback_data.session_id)
            
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail=ErrorResponse(
                        error="Session not found",
                        detail=f"Session {feedback_data.session_id} does not exist",
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                        request_id=request_id
                    ).dict()
                )
            
            # Проверяем, не была ли уже оставлена обратная связь
            feedback_repo = FeedbackRepository(db)
            existing_feedback = await feedback_repo.get_session_feedback(feedback_data.session_id)
            
            if existing_feedback:
                logger.warning(f"Feedback already exists for session {feedback_data.session_id}")
                return FeedbackResponse(
                    feedback_id=str(existing_feedback.id),
                    session_id=feedback_data.session_id,
                    was_helpful=existing_feedback.was_helpful,
                    helped_decision=existing_feedback.helped_decision,
                    rating=existing_feedback.rating,
                    comment=existing_feedback.comment,
                    created_at=existing_feedback.created_at.isoformat(),
                    message="Обратная связь уже была оставлена ранее. Спасибо!"
                )
            
            # Создаем новую обратную связь
            feedback = await feedback_repo.create_feedback(
                session_id=feedback_data.session_id,
                was_helpful=feedback_data.was_helpful,
                helped_decision=feedback_data.helped_decision,
                rating=feedback_data.rating,
                comment=feedback_data.comment
            )
            
            logger.info(f"Feedback submitted for session {feedback_data.session_id}: helpful={feedback_data.was_helpful}, decision={feedback_data.helped_decision}")
            
            # Обновляем состояние графа
            try:
                state = await graph_instance.get_session_state(feedback_data.session_id)
                if state:
                    state["feedback_received"] = True
                    await graph_instance.redis_manager.save_session_state(feedback_data.session_id, state)
            except Exception as e:
                logger.warning(f"Failed to update graph state with feedback: {str(e)}")
            
            return FeedbackResponse(
                feedback_id=str(feedback.id),
                session_id=feedback_data.session_id,
                was_helpful=feedback.was_helpful,
                helped_decision=feedback.helped_decision,
                rating=feedback.rating,
                comment=feedback.comment,
                created_at=feedback.created_at.isoformat(),
                message="Спасибо за обратную связь! Это поможет нам улучшить систему."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="Internal server error",
                detail="Failed to submit feedback",
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                request_id=request_id
            ).dict()
        )


@app.get("/api/v1/feedback/stats")
@track_api_metrics("GET", "/api/v1/feedback/stats")
async def get_feedback_stats(days: int = 30):
    """Получение статистики обратной связи"""
    try:
        async with get_db_session() as db:
            feedback_repo = FeedbackRepository(db)
            stats = await feedback_repo.get_feedback_stats(days=days)
            return stats
    except Exception as e:
        logger.error(f"Error getting feedback stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get feedback stats")


@app.get("/api/v1/cache/stats")
@track_api_metrics("GET", "/api/v1/cache/stats")
async def get_cache_stats():
    """Получение статистики кэширования агентов"""
    try:
        from app.core.ai_studio import get_ai_studio_client
        client = await get_ai_studio_client()
        stats = await client.get_cache_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get cache stats")


@app.get("/api/v1/metrics/performance")
@track_api_metrics("GET", "/api/v1/metrics/performance")
async def get_performance_metrics_endpoint(node: Optional[str] = None, hours: int = 24):
    """Получение метрик производительности узлов
    
    Args:
        node: Имя узла (опционально, если не указано - возвращает все узлы)
        hours: Количество часов для анализа (по умолчанию 24)
    """
    try:
        from app.core.metrics import get_performance_metrics
        metrics = await get_performance_metrics()
        
        if node:
            # Статистика для конкретного узла
            stats = await metrics.get_node_statistics(node, hours)
            return {"node": node, "hours": hours, "statistics": stats}
        else:
            # Статистика для всех узлов
            nodes = ["intake", "data_completeness_checker", "triage", "hypothesis_generator",
                     "infection", "immune", "oncology", "rare_disease", "synthesis"]
            all_stats = {}
            for node_name in nodes:
                all_stats[node_name] = await metrics.get_node_statistics(node_name, hours)
            return {"hours": hours, "statistics": all_stats}
    except Exception as e:
        logger.error(f"Error getting performance metrics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get performance metrics")


@app.get("/api/v1/metrics/performance/{session_id}")
@track_api_metrics("GET", "/api/v1/metrics/performance/{session_id}")
async def get_session_performance_metrics(session_id: str):
    """Получение метрик производительности для конкретной сессии"""
    try:
        from app.core.metrics import get_performance_metrics
        metrics = await get_performance_metrics()
        stats = await metrics.get_chain_statistics(session_id)
        return {"session_id": session_id, "statistics": stats}
    except Exception as e:
        logger.error(f"Error getting session performance metrics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get session performance metrics")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )