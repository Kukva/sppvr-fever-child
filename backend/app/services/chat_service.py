"""Сервис для работы с чатом"""

import uuid
import asyncio
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime

from app.core.langgraph_app import get_fever_routing_graph
from app.db.repositories import SessionRepository, MessageRepository
from app.db.session import get_db_session
from app.utils.metrics import (
    increment_active_sessions, decrement_active_sessions,
    record_session_created, record_session_completed, record_session_error,
    record_session_duration, record_questions_count
)
from app.utils.logging import log_session_activity, AgentLogger
import logging

logger = logging.getLogger(__name__)


class ChatService:
    """Сервис для управления чатом и сессиями"""
    
    def __init__(self):
        self.graph = None
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self):
        """Инициализация сервиса"""
        self.graph = await get_fever_routing_graph()
        logger.info("Chat service initialized")
    
    async def create_session(
        self,
        doctor_id: Optional[str] = None,
        patient_initial_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Создание новой сессии чата"""
        
        try:
            session_id = str(uuid.uuid4())
            
            # Создание сессии в графе
            await self.graph.create_session(session_id, doctor_id)
            
            # Сохранение в базу данных
            async with get_db_session() as db:
                session_repo = SessionRepository(db)
                session = await session_repo.create_session(
                    session_id=session_id,
                    doctor_id=doctor_id,
                    patient_age_years=patient_initial_data.get("age_years") if patient_initial_data else None,
                    patient_age_months=patient_initial_data.get("age_months") if patient_initial_data else None
                )
            
            # Регистрация активной сессии
            self.active_sessions[session_id] = {
                "created_at": datetime.utcnow(),
                "doctor_id": doctor_id,
                "message_count": 0,
                "last_activity": datetime.utcnow()
            }
            
            # Обновление метрик
            increment_active_sessions()
            record_session_created()
            
            # Логирование
            await log_session_activity(
                session_id=session_id,
                activity="session_created",
                metadata={"doctor_id": doctor_id}
            )
            
            logger.info(f"Created new chat session {session_id}")
            
            return {
                "session_id": session_id,
                "created_at": session.created_at.isoformat(),
                "status": "active",
                "message": "Сессия создана. Пожалуйста, введите информацию о пациенте."
            }
            
        except ValueError as e:
            logger.error(f"Validation error creating chat session: {str(e)}")
            record_session_error()
            raise ValueError(f"Invalid session data: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating chat session: {str(e)}", exc_info=True)
            record_session_error()
            raise RuntimeError(f"Failed to create chat session: {str(e)}")
    
    async def send_message(
        self,
        session_id: str,
        message: str,
        doctor_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Отправка сообщения в чат. progress_callback(agent_key, title_ru, description) вызывается после каждого шага графа при стриминге."""
        
        try:
            logger.info(f"Processing message for session {session_id}")
            
            # Проверка существования сессии
            if session_id not in self.active_sessions:
                logger.info(f"Session {session_id} not in active sessions, attempting to restore")
                
                # Попытка загрузить сессию из базы
                async with get_db_session() as db:
                    session_repo = SessionRepository(db)
                    session = await session_repo.get_session(session_id)
                    
                    if not session:
                        logger.error(f"Session {session_id} not found in database")
                        raise ValueError(f"Session {session_id} not found")
                    
                    # Проверяем, существует ли сессия в графе
                    session_state = await self.graph.get_session_state(session_id)
                    if not session_state:
                        logger.info(f"Creating session {session_id} in graph")
                        await self.graph.create_session(session_id, session.doctor_id)
                    
                    # Восстановление активной сессии
                    self.active_sessions[session_id] = {
                        "created_at": session.created_at,
                        "doctor_id": session.doctor_id,
                        "message_count": 0,
                        "last_activity": datetime.utcnow()
                    }
                    
                    logger.info(f"Session {session_id} restored and registered in active sessions")
            
            # Обновление активности сессии
            self.active_sessions[session_id]["last_activity"] = datetime.utcnow()
            self.active_sessions[session_id]["message_count"] += 1
            
            logger.info(f"Processing message through graph for session {session_id}")
            
            # Обработка сообщения через граф с таймаутом (при progress_callback используется astream)
            result = await self.graph.process_message(
                session_id=session_id,
                message=message,
                timeout=300,  # 5 минут таймаут
                progress_callback=progress_callback,
            )

            # Граф может вернуть success=False, но с уже сформированным response (таймаут, сбой и т.д.).
            # Не поднимаем исключение — иначе WebSocket шлёт только type:error без пузыря в чате.
            if not result.get("success"):
                err = result.get("error")
                logger.error(
                    "Graph processing failed for session %s: %s",
                    session_id,
                    err,
                )
                resp = (result.get("response") or "").strip()
                if not resp:
                    err_s = (str(err).strip() if err else "")
                    resp = err_s or (
                        "Этот случай не похож на типичные, поэтому я не могу дать ответ. "
                        "Уточните клиническую картину или обратитесь к врачу очно."
                    )
                result = {**result, "response": resp}
            else:
                logger.info(f"Graph processing completed for session {session_id}")
            
            # Сохранение сообщений в базу данных
            async with get_db_session() as db:
                message_repo = MessageRepository(db)
                
                # Сохранение сообщения пользователя
                await message_repo.create_message(
                    session_id=session_id,
                    role="user",
                    content=message
                )
                
                # Сохранение ответа ассистента (пустой текст не сохраняем отдельно — граф уже подставляет fallback)
                resp = (result.get("response") or "").strip()
                if resp:
                    await message_repo.create_message(
                        session_id=session_id,
                        role="assistant",
                        content=resp,
                        agent_name=result.get("current_step")
                    )
            
            # Обновление метрики вопросов
            if result.get("questions_to_ask"):
                record_questions_count(len(result["questions_to_ask"]))
            
            # Логирование
            await log_session_activity(
                session_id=session_id,
                activity="message_processed",
                metadata={
                    "message_length": len(message),
                    "current_step": result.get("current_step"),
                    "urgency_level": result.get("urgency_level")
                }
            )
            
            logger.info(f"Message processing completed successfully for session {session_id}")
            
            return {
                "success": True,
                "session_id": session_id,
                "response": result["response"],
                "current_step": result.get("current_step"),
                "urgency_level": result.get("urgency_level"),
                "needs_more_info": result.get("needs_more_info", False),
                "questions_to_ask": result.get("questions_to_ask", []),
                "recommendations": result.get("recommendations"),
                "agent_workflow": result.get("agent_workflow", []),
                "clinical_sources": result.get("clinical_sources", []),
                "state": result.get("state"),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except ValueError as e:
            logger.error(f"Validation error processing message in session {session_id}: {str(e)}")
            record_session_error()
            raise ValueError(f"Invalid message data: {str(e)}")
        except TimeoutError as e:
            logger.error(f"Timeout processing message in session {session_id}: {str(e)}")
            record_session_error()
            raise TimeoutError(f"Message processing timeout: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing message in session {session_id}: {str(e)}", exc_info=True)
            record_session_error()
            raise RuntimeError(f"Failed to process message: {str(e)}")
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение информации о сессии"""
        
        try:
            # Получение состояния из графа
            state = await self.graph.get_session_state(session_id)
            
            if not state:
                return None
            
            # Получение информации из базы данных
            async with get_db_session() as db:
                session_repo = SessionRepository(db)
                session = await session_repo.get_session(session_id)
                
                if not session:
                    return None
            
            # Получение истории сообщений
            async with get_db_session() as db:
                message_repo = MessageRepository(db)
                messages = await message_repo.get_session_messages(session_id)
            
            return {
                "session_id": session_id,
                "doctor_id": session.doctor_id,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "status": session.status,
                "urgency_level": state.get("urgency_level"),
                "current_step": state.get("current_step"),
                "message_count": len(messages),
                "needs_more_info": state.get("needs_more_info", False),
                "has_recommendations": bool(state.get("synthesis_output")),
                "active": session_id in self.active_sessions
            }
            
        except Exception as e:
            logger.error(f"Error getting session info {session_id}: {str(e)}")
            return None
    
    async def get_chat_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение истории чата"""
        
        try:
            async with get_db_session() as db:
                message_repo = MessageRepository(db)
                messages = await message_repo.get_session_messages(session_id)
            
            # Преобразование в формат API
            history = []
            for msg in messages[-limit:]:
                history.append({
                    "message_id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat(),
                    "agent_name": msg.agent_name
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting chat history for session {session_id}: {str(e)}")
            return []
    
    async def end_session(self, session_id: str) -> Dict[str, Any]:
        """Завершение сессии"""
        
        try:
            # Удаление из активных сессий
            if session_id in self.active_sessions:
                session_info = self.active_sessions[session_id]
                duration = (datetime.utcnow() - session_info["created_at"]).total_seconds()
                
                del self.active_sessions[session_id]
                
                # Обновление метрик
                decrement_active_sessions()
                record_session_completed()
                record_session_duration(duration)
            
            # Обновление статуса в базе данных
            async with get_db_session() as db:
                session_repo = SessionRepository(db)
                await session_repo.update_session_status(session_id, "completed")
            
            # Логирование
            await log_session_activity(
                session_id=session_id,
                activity="session_completed"
            )
            
            logger.info(f"Ended chat session {session_id}")
            
            return {
                "session_id": session_id,
                "status": "completed",
                "message": "Сессия завершена"
            }
            
        except Exception as e:
            logger.error(f"Error ending session {session_id}: {str(e)}")
            raise
    
    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Получение списка активных сессий"""
        
        try:
            active_sessions_info = []
            
            for session_id, session_info in self.active_sessions.items():
                # Получение дополнительной информации
                session_data = await self.get_session_info(session_id)
                
                if session_data:
                    active_sessions_info.append({
                        **session_data,
                        "message_count": session_info["message_count"],
                        "last_activity": session_info["last_activity"].isoformat()
                    })
            
            # Сортировка по последней активности
            active_sessions_info.sort(
                key=lambda x: x["last_activity"],
                reverse=True
            )
            
            return active_sessions_info
            
        except Exception as e:
            logger.error(f"Error getting active sessions: {str(e)}")
            return []
    
    async def cleanup_inactive_sessions(self, timeout_hours: int = 24):
        """Очистка неактивных сессий"""
        
        try:
            current_time = datetime.utcnow()
            inactive_sessions = []
            
            for session_id, session_info in self.active_sessions.items():
                last_activity = session_info["last_activity"]
                inactive_duration = (current_time - last_activity).total_seconds()
                
                if inactive_duration > timeout_hours * 3600:
                    inactive_sessions.append(session_id)
            
            # Завершение неактивных сессий
            for session_id in inactive_sessions:
                await self.end_session(session_id)
                logger.info(f"Cleaned up inactive session {session_id}")
            
            if inactive_sessions:
                logger.info(f"Cleaned up {len(inactive_sessions)} inactive sessions")
            
        except Exception as e:
            logger.error(f"Error during session cleanup: {str(e)}")
    
    async def get_session_statistics(self) -> Dict[str, Any]:
        """Получение статистики по сессиям"""
        
        try:
            async with get_db_session() as db:
                session_repo = SessionRepository(db)
                
                # Общая статистика
                total_sessions = len(await session_repo.get_active_sessions(1000))
                active_sessions_count = len(self.active_sessions)
                
                # Статистика по уровням срочности
                urgency_stats = {}
                for session_id in self.active_sessions:
                    session_info = await self.get_session_info(session_id)
                    if session_info:
                        urgency = session_info.get("urgency_level", "unknown")
                        urgency_stats[urgency] = urgency_stats.get(urgency, 0) + 1
                
                return {
                    "total_sessions": total_sessions,
                    "active_sessions": active_sessions_count,
                    "urgency_distribution": urgency_stats,
                    "average_messages_per_session": sum(
                        info["message_count"] for info in self.active_sessions.values()
                    ) / max(active_sessions_count, 1)
                }
                
        except Exception as e:
            logger.error(f"Error getting session statistics: {str(e)}")
            return {
                "total_sessions": 0,
                "active_sessions": 0,
                "urgency_distribution": {},
                "average_messages_per_session": 0
            }
    
    async def validate_session_access(self, session_id: str, doctor_id: Optional[str] = None) -> bool:
        """Проверка доступа к сессии"""
        
        try:
            # Если doctor_id не указан, разрешаем доступ (для тестирования)
            if not doctor_id:
                return True
            
            # Проверка существования сессии
            session_info = await self.get_session_info(session_id)
            if not session_info:
                return False
            
            # Проверка принадлежности сессии врачу
            if session_info.get("doctor_id") and session_info["doctor_id"] != doctor_id:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating session access: {str(e)}")
            return False