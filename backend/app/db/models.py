"""SQLAlchemy модели базы данных"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, JSON, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class Session(Base):
    """Модель сессии консультации"""
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    status = Column(String(50), default='active')  # active, completed, archived
    urgency_level = Column(String(50), nullable=True)  # emergency, urgent, routine
    patient_age_years = Column(Integer, nullable=True)
    patient_age_months = Column(Integer, nullable=True)
    
    # Отношения
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    patient_data = relationship("PatientData", back_populates="session", cascade="all, delete-orphan")
    agent_outputs = relationship("AgentOutput", back_populates="session", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="session", cascade="all, delete-orphan")
    system_logs = relationship("SystemLog", back_populates="session", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """Модель сообщений диалога"""
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    agent_name = Column(String(100), nullable=True)  # intake, triage, infection, etc.
    message_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Отношения
    session = relationship("Session", back_populates="messages")


class PatientData(Base):
    """Модель данных пациента"""
    __tablename__ = "patient_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    age_years = Column(Integer, nullable=True)
    age_months = Column(Integer, nullable=True)
    temperature_current = Column(Float, nullable=True)
    temperature_max = Column(Float, nullable=True)
    temperature_pattern = Column(String(50), nullable=True)
    duration_days = Column(Integer, nullable=True)
    symptoms = Column(JSON, nullable=True)  # массив симптомов
    red_flags = Column(JSON, nullable=True)  # массив красных флагов
    anamnesis = Column(JSON, nullable=True)
    physical_exam = Column(JSON, nullable=True)
    lab_results = Column(JSON, nullable=True)
    missing_info = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Отношения
    session = relationship("Session", back_populates="patient_data")


class AgentOutput(Base):
    """Модель результатов работы агентов"""
    __tablename__ = "agent_outputs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(100), nullable=False)
    output = Column(JSON, nullable=False)
    confidence = Column(Float, nullable=True)
    questions_needed = Column(JSON, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Отношения
    session = relationship("Session", back_populates="agent_outputs")


class Recommendation(Base):
    """Модель финальных рекомендаций"""
    __tablename__ = "recommendations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    urgency_level = Column(String(50), nullable=True)
    primary_specialist = Column(JSON, nullable=True)  # SpecialistRecommendation
    additional_specialists = Column(JSON, nullable=True)  # массив SpecialistRecommendation
    reasoning = Column(Text, nullable=True)
    required_tests = Column(JSON, nullable=True)
    red_flags = Column(JSON, nullable=True)
    recommendations_text = Column(Text, nullable=True)
    pdf_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Отношения
    session = relationship("Session", back_populates="recommendations")


class SystemLog(Base):
    """Модель системных логов"""
    __tablename__ = "system_logs"
    
    id = Column(BigInteger, primary_key=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    level = Column(String(20), nullable=False)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger_name = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    exception = Column(Text, nullable=True)
    log_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Отношения
    session = relationship("Session", back_populates="system_logs")


# LangGraph Checkpoint таблицы
class Checkpoint(Base):
    """Таблица для LangGraph checkpointer"""
    __tablename__ = "checkpoints"
    
    thread_id = Column(String, primary_key=True, nullable=False)
    checkpoint_ns = Column(String, primary_key=True, nullable=False, default='')
    checkpoint_id = Column(String, primary_key=True, nullable=False)
    parent_checkpoint_id = Column(String, nullable=True)
    type = Column(String, nullable=True)
    checkpoint = Column(JSON, nullable=False)
    checkpoint_metadata = Column(JSON, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CheckpointWrite(Base):
    """Таблица записей checkpointer"""
    __tablename__ = "checkpoint_writes"
    
    thread_id = Column(String, primary_key=True, nullable=False)
    checkpoint_ns = Column(String, primary_key=True, nullable=False, default='')
    checkpoint_id = Column(String, primary_key=True, nullable=False)
    task_id = Column(String, primary_key=True, nullable=False)
    idx = Column(Integer, primary_key=True, nullable=False)
    channel = Column(String, nullable=False)
    type = Column(String, nullable=True)
    value = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    """Модель обратной связи от пользователей"""
    __tablename__ = "feedback"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    was_helpful = Column(Boolean, nullable=False)  # Была ли рекомендация полезной
    helped_decision = Column(Boolean, nullable=False)  # Помогла ли принять решение
    rating = Column(Integer, nullable=True)  # Оценка от 1 до 5
    comment = Column(Text, nullable=True)  # Дополнительный комментарий
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Отношения
    session = relationship("Session", back_populates="feedback")