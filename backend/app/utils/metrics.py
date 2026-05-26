"""Prometheus метрики и мониторинг"""

import time
import functools
from typing import Dict, Any, Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
import logging

logger = logging.getLogger(__name__)

# Создание реестра метрик
registry = CollectorRegistry()

# Метрики для агентов
agent_requests_total = Counter(
    'agent_requests_total',
    'Total number of agent requests',
    ['agent_name', 'status'],
    registry=registry
)

agent_execution_time = Histogram(
    'agent_execution_seconds',
    'Agent execution time in seconds',
    ['agent_name'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=registry
)

agent_errors_total = Counter(
    'agent_errors_total',
    'Total number of agent errors',
    ['agent_name', 'error_type'],
    registry=registry
)

# Метрики для сессий
active_sessions = Gauge(
    'active_sessions_total',
    'Number of active sessions',
    registry=registry
)

session_duration = Histogram(
    'session_duration_seconds',
    'Session duration in seconds',
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400],  # 1мин, 5мин, 10мин, 30мин, 1ч, 2ч, 4ч
    registry=registry
)

sessions_total = Counter(
    'sessions_total',
    'Total number of sessions',
    ['status'],  # created, completed, error
    registry=registry
)

# Метрики для API
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status_code'],
    registry=registry
)

api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
    registry=registry
)

api_errors_total = Counter(
    'api_errors_total',
    'Total API errors',
    ['method', 'endpoint', 'error_type'],
    registry=registry
)

# Метрики для AI Studio
ai_studio_requests_total = Counter(
    'ai_studio_requests_total',
    'Total AI Studio API requests',
    ['agent_name', 'status'],
    registry=registry
)

ai_studio_request_duration = Histogram(
    'ai_studio_request_duration_seconds',
    'AI Studio request duration',
    ['agent_name'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=registry
)

ai_studio_errors_total = Counter(
    'ai_studio_errors_total',
    'Total AI Studio errors',
    ['agent_name', 'error_type'],
    registry=registry
)

# Метрики для базы данных
db_connections_active = Gauge(
    'db_connections_active',
    'Number of active database connections',
    registry=registry
)

db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['operation'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
    registry=registry
)

db_errors_total = Counter(
    'db_errors_total',
    'Total database errors',
    ['operation', 'error_type'],
    registry=registry
)

# Метрики для системы
system_memory_usage = Gauge(
    'system_memory_usage_bytes',
    'System memory usage in bytes',
    registry=registry
)

system_cpu_usage = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    registry=registry
)

# Метрики для PDF генерации
pdf_generation_total = Counter(
    'pdf_generation_total',
    'Total PDF generations',
    ['status'],
    registry=registry
)

pdf_generation_duration = Histogram(
    'pdf_generation_duration_seconds',
    'PDF generation duration',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
    registry=registry
)

# Метрики качества
recommendations_confidence = Histogram(
    'recommendations_confidence_score',
    'Confidence score of recommendations',
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    registry=registry
)

questions_per_session = Histogram(
    'questions_per_session_total',
    'Number of questions asked per session',
    buckets=[1, 2, 3, 5, 10, 15, 20],
    registry=registry
)


def track_agent_metrics(agent_name: str):
    """Декоратор для отслеживания метрик агентов"""
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'
            error_type = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                error_type = type(e).__name__
                agent_errors_total.labels(
                    agent_name=agent_name,
                    error_type=error_type
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                
                # Обновление метрик
                agent_requests_total.labels(
                    agent_name=agent_name,
                    status=status
                ).inc()
                
                agent_execution_time.labels(
                    agent_name=agent_name
                ).observe(duration)
                
                logger.debug(
                    f"Agent {agent_name} metrics: duration={duration:.3f}s, status={status}"
                )
        
        return wrapper
    return decorator


def track_api_metrics(method: str, endpoint: str):
    """Декоратор для отслеживания метрик API"""
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status_code = 200
            error_type = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = 500
                error_type = type(e).__name__
                api_errors_total.labels(
                    method=method,
                    endpoint=endpoint,
                    error_type=error_type
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                
                # Обновление метрик
                api_requests_total.labels(
                    method=method,
                    endpoint=endpoint,
                    status_code=str(status_code)
                ).inc()
                
                api_request_duration.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(duration)
                
                logger.debug(
                    f"API {method} {endpoint}: duration={duration:.3f}s, status={status_code}"
                )
        
        return wrapper
    return decorator


def track_ai_studio_metrics(agent_name: str):
    """Декоратор для отслеживания метрик AI Studio"""
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'
            error_type = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                error_type = type(e).__name__
                ai_studio_errors_total.labels(
                    agent_name=agent_name,
                    error_type=error_type
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                
                # Обновление метрик
                ai_studio_requests_total.labels(
                    agent_name=agent_name,
                    status=status
                ).inc()
                
                ai_studio_request_duration.labels(
                    agent_name=agent_name
                ).observe(duration)
        
        return wrapper
    return decorator


def track_db_metrics(operation: str):
    """Декоратор для отслеживания метрик базы данных"""
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            error_type = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error_type = type(e).__name__
                db_errors_total.labels(
                    operation=operation,
                    error_type=error_type
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                db_query_duration.labels(operation=operation).observe(duration)
        
        return wrapper
    return decorator


def track_pdf_metrics():
    """Декоратор для отслеживания метрик PDF генерации"""
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                duration = time.time() - start_time
                
                pdf_generation_total.labels(status=status).inc()
                pdf_generation_duration.observe(duration)
        
        return wrapper
    return decorator


# Функции для обновления метрик

def increment_active_sessions():
    """Увеличение счетчика активных сессий"""
    active_sessions.inc()


def decrement_active_sessions():
    """Уменьшение счетчика активных сессий"""
    active_sessions.dec()


def record_session_created():
    """Запись создания сессии"""
    sessions_total.labels(status='created').inc()


def record_session_completed():
    """Запись завершения сессии"""
    sessions_total.labels(status='completed').inc()


def record_session_error():
    """Запись ошибки сессии"""
    sessions_total.labels(status='error').inc()


def record_session_duration(duration_seconds: float):
    """Запись длительности сессии"""
    session_duration.observe(duration_seconds)


def record_recommendation_confidence(confidence_score: float):
    """Запись уверенности рекомендаций"""
    recommendations_confidence.observe(confidence_score)


def record_questions_count(questions_count: int):
    """Запись количества вопросов в сессии"""
    questions_per_session.observe(questions_count)


def update_system_metrics():
    """Обновление системных метрик"""
    try:
        import psutil
        
        # Использование памяти
        memory = psutil.virtual_memory()
        system_memory_usage.set(memory.used)
        
        # Использование CPU
        cpu_percent = psutil.cpu_percent()
        system_cpu_usage.set(cpu_percent)
        
    except ImportError:
        logger.warning("psutil not available, system metrics disabled")
    except Exception as e:
        logger.error(f"Error updating system metrics: {str(e)}")


def get_metrics() -> str:
    """Получение метрик в формате Prometheus"""
    try:
        # Обновление системных метрик
        update_system_metrics()
        
        # Генерация метрик
        return generate_latest(registry)
    except Exception as e:
        logger.error(f"Error generating metrics: {str(e)}")
        return ""


def get_metrics_summary() -> Dict[str, Any]:
    """Получение сводки метрик"""
    try:
        # Сбор метрик в удобном формате
        summary = {
            'active_sessions': active_sessions._value.get(),
            'total_sessions_created': sessions_total.labels(status='created')._value.get(),
            'total_sessions_completed': sessions_total.labels(status='completed')._value.get(),
            'total_sessions_errors': sessions_total.labels(status='error')._value.get(),
            'system_memory_bytes': system_memory_usage._value.get(),
            'system_cpu_percent': system_cpu_usage._value.get(),
        }
        
        # Добавление метрик агентов
        agent_metrics = {}
        for agent_name in ['intake', 'triage', 'infection', 'immune', 'oncology', 'rare_disease', 'question', 'synthesis']:
            agent_metrics[agent_name] = {
                'requests_total': agent_requests_total.labels(agent_name=agent_name, status='success')._value.get(),
                'errors_total': agent_errors_total.labels(agent_name=agent_name, error_type='Exception')._value.get(),
                'avg_execution_time': agent_execution_time.labels(agent_name=agent_name).observe() if hasattr(agent_execution_time.labels(agent_name=agent_name), 'observe') else 0
            }
        
        summary['agents'] = agent_metrics
        
        return summary
        
    except Exception as e:
        logger.error(f"Error generating metrics summary: {str(e)}")
        return {}


class MetricsContext:
    """Контекст для отслеживания метрик операции"""
    
    def __init__(self, operation_type: str, **labels):
        self.operation_type = operation_type
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            
            if exc_type is None:
                # Успешное завершение
                self._record_success(duration)
            else:
                # Ошибка
                self._record_error(duration, exc_type)
    
    def _record_success(self, duration: float):
        """Запись успешного завершения"""
        pass
    
    def _record_error(self, duration: float, error_type):
        """Запись ошибки"""
        pass


# Декоратор для контекстного менеджера метрик
def metrics_context(operation_type: str, **labels):
    """Декоратор для создания контекста метрик"""
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            with MetricsContext(operation_type, **labels):
                return await func(*args, **kwargs)
        return wrapper
    return decorator