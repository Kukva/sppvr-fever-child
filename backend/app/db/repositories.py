"""Репозитории для работы с базой данных"""

import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.orm import selectinload

from app.db.models import (
    Session, Message, PatientData, AgentOutput, 
    Recommendation, SystemLog, Feedback
)
import logging

logger = logging.getLogger(__name__)


class BaseRepository:
    """Базовый репозиторий"""
    
    def __init__(self, db: AsyncSession):
        self.db = db


class SessionRepository(BaseRepository):
    """Репозиторий для работы с сессиями"""
    
    async def create_session(
        self,
        session_id: str,
        doctor_id: Optional[str] = None,
        patient_age_years: Optional[int] = None,
        patient_age_months: Optional[int] = None
    ) -> Session:
        """Создание новой сессии"""
        
        db_session = Session(
            id=session_id,
            doctor_id=doctor_id,
            patient_age_years=patient_age_years,
            patient_age_months=patient_age_months
        )
        
        self.db.add(db_session)
        await self.db.commit()
        await self.db.refresh(db_session)
        
        return db_session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Получение сессии по ID"""
        
        stmt = select(Session).where(Session.id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_session_status(self, session_id: str, status: str) -> bool:
        """Обновление статуса сессии"""
        
        stmt = (
            update(Session)
            .where(Session.id == session_id)
            .values(
                status=status,
                updated_at=datetime.utcnow()
            )
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        return result.rowcount > 0
    
    async def update_session_urgency(self, session_id: str, urgency_level: str) -> bool:
        """Обновление уровня срочности сессии"""
        
        stmt = (
            update(Session)
            .where(Session.id == session_id)
            .values(
                urgency_level=urgency_level,
                updated_at=datetime.utcnow()
            )
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        return result.rowcount > 0
    
    async def get_active_sessions(self, limit: int = 100) -> List[Session]:
        """Получение активных сессий"""
        
        stmt = (
            select(Session)
            .where(Session.status == 'active')
            .order_by(Session.updated_at.desc())
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_sessions_by_doctor(self, doctor_id: str, limit: int = 50) -> List[Session]:
        """Получение сессий врача"""
        
        stmt = (
            select(Session)
            .where(Session.doctor_id == doctor_id)
            .order_by(Session.updated_at.desc())
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_all_sessions(self, limit: int = 100, offset: int = 0) -> List[Session]:
        """Получение всех сессий (для истории)"""
        
        stmt = (
            select(Session)
            .order_by(Session.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_sessions_count(self) -> int:
        """Получение общего количества сессий"""
        
        from sqlalchemy import func
        stmt = select(func.count(Session.id))
        result = await self.db.execute(stmt)
        return result.scalar() or 0


class MessageRepository(BaseRepository):
    """Репозиторий для работы с сообщениями"""
    
    async def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Создание нового сообщения"""
        
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            agent_name=agent_name,
            metadata=metadata or {}
        )
        
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        
        return message
    
    async def get_session_messages(self, session_id: str) -> List[Message]:
        """Получение всех сообщений сессии"""
        
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_last_message(self, session_id: str) -> Optional[Message]:
        """Получение последнего сообщения сессии"""
        
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_messages_by_agent(self, session_id: str, agent_name: str) -> List[Message]:
        """Получение сообщений от конкретного агента"""
        
        stmt = (
            select(Message)
            .where(
                and_(
                    Message.session_id == session_id,
                    Message.agent_name == agent_name
                )
            )
            .order_by(Message.created_at.asc())
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()


class PatientDataRepository(BaseRepository):
    """Репозиторий для работы с данными пациентов"""
    
    async def create_or_update_patient_data(
        self,
        session_id: str,
        patient_data: Dict[str, Any]
    ) -> PatientData:
        """Создание или обновление данных пациента"""
        
        # Проверка существования данных
        existing = await self.get_patient_data(session_id)
        
        if existing:
            # Обновление существующих данных
            for key, value in patient_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            
            existing.updated_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Создание новых данных
            new_data = PatientData(session_id=session_id, **patient_data)
            self.db.add(new_data)
            await self.db.commit()
            await self.db.refresh(new_data)
            return new_data
    
    async def get_patient_data(self, session_id: str) -> Optional[PatientData]:
        """Получение данных пациента по ID сессии"""
        
        stmt = select(PatientData).where(PatientData.session_id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class AgentOutputRepository(BaseRepository):
    """Репозиторий для работы с результатами агентов"""
    
    async def create_agent_output(
        self,
        session_id: str,
        agent_name: str,
        output: Dict[str, Any],
        confidence: Optional[float] = None,
        questions_needed: Optional[List[str]] = None,
        execution_time_ms: Optional[int] = None
    ) -> AgentOutput:
        """Создание записи о результате работы агента"""
        
        agent_output = AgentOutput(
            session_id=session_id,
            agent_name=agent_name,
            output=output,
            confidence=confidence,
            questions_needed=questions_needed or [],
            execution_time_ms=execution_time_ms
        )
        
        self.db.add(agent_output)
        await self.db.commit()
        await self.db.refresh(agent_output)
        
        return agent_output
    
    async def get_session_agent_outputs(self, session_id: str) -> List[AgentOutput]:
        """Получение всех результатов агентов для сессии"""
        
        stmt = (
            select(AgentOutput)
            .where(AgentOutput.session_id == session_id)
            .order_by(AgentOutput.created_at.asc())
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_agent_output(self, session_id: str, agent_name: str) -> Optional[AgentOutput]:
        """Получение результата конкретного агента"""
        
        stmt = (
            select(AgentOutput)
            .where(
                and_(
                    AgentOutput.session_id == session_id,
                    AgentOutput.agent_name == agent_name
                )
            )
            .order_by(AgentOutput.created_at.desc())
            .limit(1)
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class RecommendationRepository(BaseRepository):
    """Репозиторий для работы с рекомендациями"""
    
    async def create_recommendation(
        self,
        session_id: str,
        urgency_level: str,
        primary_specialist: Dict[str, Any],
        additional_specialists: List[Dict[str, Any]],
        reasoning: Optional[str] = None,
        required_tests: Optional[List[str]] = None,
        red_flags: Optional[List[str]] = None,
        recommendations_text: Optional[str] = None,
        pdf_path: Optional[str] = None
    ) -> Recommendation:
        """Создание рекомендации"""
        
        recommendation = Recommendation(
            session_id=session_id,
            urgency_level=urgency_level,
            primary_specialist=primary_specialist,
            additional_specialists=additional_specialists,
            reasoning=reasoning,
            required_tests=required_tests or [],
            red_flags=red_flags or [],
            recommendations_text=recommendations_text,
            pdf_path=pdf_path
        )
        
        self.db.add(recommendation)
        await self.db.commit()
        await self.db.refresh(recommendation)
        
        return recommendation
    
    async def get_session_recommendations(self, session_id: str) -> Optional[Recommendation]:
        """Получение рекомендаций для сессии"""
        
        stmt = (
            select(Recommendation)
            .where(Recommendation.session_id == session_id)
            .order_by(Recommendation.created_at.desc())
            .limit(1)
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_pdf_path(self, recommendation_id: uuid.UUID, pdf_path: str) -> bool:
        """Обновление пути к PDF файлу"""
        
        stmt = (
            update(Recommendation)
            .where(Recommendation.id == recommendation_id)
            .values(pdf_path=pdf_path)
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        return result.rowcount > 0


class SystemLogRepository(BaseRepository):
    """Репозиторий для работы с системными логами"""
    
    async def create_log(
        self,
        level: str,
        message: str,
        logger_name: Optional[str] = None,
        session_id: Optional[str] = None,
        exception: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SystemLog:
        """Создание записи в логе"""
        
        log_entry = SystemLog(
            session_id=session_id,
            level=level,
            logger_name=logger_name,
            message=message,
            exception=exception,
            metadata=metadata or {}
        )
        
        self.db.add(log_entry)
        await self.db.commit()
        await self.db.refresh(log_entry)
        
        return log_entry
    
    async def get_session_logs(
        self,
        session_id: str,
        level: Optional[str] = None,
        limit: int = 100
    ) -> List[SystemLog]:
        """Получение логов сессии"""
        
        stmt = select(SystemLog).where(SystemLog.session_id == session_id)
        
        if level:
            stmt = stmt.where(SystemLog.level == level)
        
        stmt = stmt.order_by(SystemLog.created_at.desc()).limit(limit)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_error_logs(self, hours: int = 24, limit: int = 100) -> List[SystemLog]:
        """Получение логов ошибок за последние часы"""
        
        stmt = (
            select(SystemLog)
            .where(
                and_(
                    SystemLog.level.in_(['ERROR', 'CRITICAL']),
                    SystemLog.created_at >= datetime.utcnow() - timedelta(hours=hours)
                )
            )
            .order_by(SystemLog.created_at.desc())
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def cleanup_old_logs(self, days: int = 30) -> int:
        """Очистка старых логов"""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = delete(SystemLog).where(SystemLog.created_at < cutoff_date)
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        return result.rowcount


# Импорт timedelta для cleanup_old_logs
from datetime import timedelta


class FeedbackRepository(BaseRepository):
    """Репозиторий для работы с обратной связью"""
    
    async def create_feedback(
        self,
        session_id: str,
        was_helpful: bool,
        helped_decision: bool,
        rating: Optional[int] = None,
        comment: Optional[str] = None
    ) -> Feedback:
        """Создание записи обратной связи"""
        
        feedback = Feedback(
            session_id=session_id,
            was_helpful=was_helpful,
            helped_decision=helped_decision,
            rating=rating,
            comment=comment
        )
        
        self.db.add(feedback)
        await self.db.commit()
        await self.db.refresh(feedback)
        
        return feedback
    
    async def get_session_feedback(self, session_id: str) -> Optional[Feedback]:
        """Получение обратной связи для сессии"""
        
        stmt = (
            select(Feedback)
            .where(Feedback.session_id == session_id)
            .order_by(Feedback.created_at.desc())
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_feedback_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получение статистики обратной связи"""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        stmt = select(Feedback).where(Feedback.created_at >= cutoff_date)
        result = await self.db.execute(stmt)
        all_feedback = result.scalars().all()
        
        if not all_feedback:
            return {
                "total": 0,
                "helpful_percentage": 0,
                "decision_helpful_percentage": 0,
                "average_rating": 0
            }
        
        total = len(all_feedback)
        helpful_count = sum(1 for f in all_feedback if f.was_helpful)
        decision_helpful_count = sum(1 for f in all_feedback if f.helped_decision)
        ratings = [f.rating for f in all_feedback if f.rating is not None]
        
        return {
            "total": total,
            "helpful_percentage": (helpful_count / total * 100) if total > 0 else 0,
            "decision_helpful_percentage": (decision_helpful_count / total * 100) if total > 0 else 0,
            "average_rating": sum(ratings) / len(ratings) if ratings else 0
        }