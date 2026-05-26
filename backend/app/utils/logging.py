"""Настройка системы логирования"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

from sqlalchemy.orm import Session
from app.db.repositories import SystemLogRepository


class DatabaseLogHandler(logging.Handler):
    """Кастомный handler для записи логов в PostgreSQL"""
    
    def __init__(self, db_session_factory):
        super().__init__()
        self.db_session_factory = db_session_factory
    
    def emit(self, record: logging.LogRecord):
        """Запись лога в базу данных"""
        try:
            # Создание сессии базы данных
            db = self.db_session_factory()
            
            # Извлечение дополнительных данных
            session_id = getattr(record, 'session_id', None)
            agent_name = getattr(record, 'agent_name', None)
            
            # Формирование метаданных
            metadata = {
                'filename': record.filename,
                'funcName': record.funcName,
                'lineno': record.lineno,
                'process': record.process,
                'thread': record.thread
            }
            
            if agent_name:
                metadata['agent_name'] = agent_name
            
            # Создание записи в логе
            log_entry = SystemLogRepository(db)
            asyncio.create_task(
                log_entry.create_log(
                    level=record.levelname,
                    logger_name=record.name,
                    message=record.getMessage(),
                    session_id=session_id,
                    exception=self.format_exception(record.exc_info) if record.exc_info else None,
                    metadata=metadata
                )
            )
            
        except Exception as e:
            # Fallback на консоль если БД недоступна
            print(f"Failed to write log to database: {e}", file=sys.stderr)
        finally:
            try:
                db.close()
            except:
                pass
    
    def format_exception(self, exc_info):
        """Форматирование исключения"""
        if exc_info:
            import traceback
            return ''.join(traceback.format_exception(*exc_info))
        return None


class JSONFormatter(logging.Formatter):
    """JSON форматтер для структурированных логов"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Форматирование записи в JSON"""
        
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'process': record.process,
            'thread': record.thread
        }
        
        # Добавление дополнительных полей
        if hasattr(record, 'session_id'):
            log_entry['session_id'] = record.session_id
        
        if hasattr(record, 'agent_name'):
            log_entry['agent_name'] = record.agent_name
        
        if hasattr(record, 'execution_time_ms'):
            log_entry['execution_time_ms'] = record.execution_time_ms
        
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


class AgentLogger:
    """Специализированный логгер для отслеживания работы агентов"""
    
    def __init__(self, session_id: str, agent_name: str):
        self.session_id = session_id
        self.agent_name = agent_name
        self.logger = logging.getLogger(f"agent.{agent_name}")
    
    def log_agent_start(self, input_data: Dict[str, Any]):
        """Логирование начала работы агента"""
        self.logger.info(
            f"Agent {self.agent_name} started",
            extra={
                'session_id': self.session_id,
                'agent_name': self.agent_name,
                'input_data': json.dumps(input_data, default=str, ensure_ascii=False)
            }
        )
    
    def log_agent_complete(self, output_data: Dict[str, Any], execution_time_ms: int):
        """Логирование завершения работы агента"""
        self.logger.info(
            f"Agent {self.agent_name} completed in {execution_time_ms}ms",
            extra={
                'session_id': self.session_id,
                'agent_name': self.agent_name,
                'execution_time_ms': execution_time_ms,
                'output_data': json.dumps(output_data, default=str, ensure_ascii=False)
            }
        )
    
    def log_agent_error(self, error: Exception, execution_time_ms: Optional[int] = None):
        """Логирование ошибки агента"""
        extra_data = {
            'session_id': self.session_id,
            'agent_name': self.agent_name
        }
        
        if execution_time_ms:
            extra_data['execution_time_ms'] = execution_time_ms
        
        self.logger.error(
            f"Agent {self.agent_name} failed: {str(error)}",
            extra=extra_data,
            exc_info=True
        )
    
    def log_agent_retry(self, attempt: int, max_attempts: int):
        """Логирование повтора попытки"""
        self.logger.warning(
            f"Agent {self.agent_name} retry {attempt}/{max_attempts}",
            extra={
                'session_id': self.session_id,
                'agent_name': self.agent_name,
                'retry_attempt': attempt,
                'max_attempts': max_attempts
            }
        )


def setup_logging(db_session_factory=None):
    """Настройка системы логирования"""
    
    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Очистка существующих обработчиков
    root_logger.handlers.clear()
    
    # Консольный handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Форматтер для консоли
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # Добавление консольного обработчика (всегда доступен)
    root_logger.addHandler(console_handler)
    
    # Попытка настроить файловые логи (опционально для production)
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # JSON форматтер для файла
        json_formatter = JSONFormatter()
        
        # Файловый handler для всех логов
        file_handler = logging.FileHandler(log_dir / "app.log", encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)
        
        # Файловый handler для ошибок
        error_handler = logging.FileHandler(log_dir / "errors.log", encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter)
        root_logger.addHandler(error_handler)
        
        root_logger.info("File logging enabled")
    except (OSError, PermissionError) as e:
        # Если не удалось создать файловые логи, продолжаем только с консолью
        root_logger.warning(f"File logging disabled: {e}")
    
    # Database handler (если доступна БД)
    if db_session_factory:
        try:
            db_handler = DatabaseLogHandler(db_session_factory)
            db_handler.setLevel(logging.WARNING)
            root_logger.addHandler(db_handler)
            root_logger.info("Database logging enabled")
        except Exception as e:
            root_logger.warning(f"Database logging disabled: {e}")
    
    # Настройка логгеров для конкретных модулей
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("langgraph").setLevel(logging.INFO)
    
    root_logger.info("Logging system initialized")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Получение логгера с именем"""
    return logging.getLogger(name)


def log_function_call(func):
    """Декоратор для логирования вызовов функций"""
    
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = datetime.utcnow()
        
        try:
            result = func(*args, **kwargs)
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.debug(
                f"Function {func.__name__} completed in {execution_time:.3f}s",
                extra={
                    'function': func.__name__,
                    'execution_time_ms': int(execution_time * 1000)
                }
            )
            
            return result
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.error(
                f"Function {func.__name__} failed after {execution_time:.3f}s: {str(e)}",
                extra={
                    'function': func.__name__,
                    'execution_time_ms': int(execution_time * 1000)
                },
                exc_info=True
            )
            
            raise
    
    return wrapper


async def log_session_activity(session_id: str, activity: str, metadata: Optional[Dict[str, Any]] = None):
    """Логирование активности сессии"""
    logger = get_logger("session")
    
    logger.info(
        f"Session {session_id}: {activity}",
        extra={
            'session_id': session_id,
            'activity': activity,
            'metadata': metadata or {}
        }
    )


# Импорт настроек
from app.config import settings
import asyncio