"""Модуль для мониторинга производительности цепочки агентов"""

import time
import logging
from typing import Dict, Any, Optional, Callable
from functools import wraps
from datetime import datetime
import asyncio

from app.core.redis_client import get_redis_manager

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Класс для сбора метрик производительности"""
    
    def __init__(self):
        self.redis_manager = None
        self._initialized = False
    
    async def initialize(self):
        """Инициализация Redis для хранения метрик"""
        if not self._initialized:
            self.redis_manager = await get_redis_manager()
            self._initialized = True
    
    def _get_metrics_key(self, metric_name: str) -> str:
        """Получение ключа для метрики в Redis"""
        return f"fever_routing:metrics:{metric_name}"
    
    async def record_execution_time(
        self,
        node_name: str,
        execution_time_ms: float,
        session_id: Optional[str] = None
    ):
        """Запись времени выполнения узла
        
        Args:
            node_name: Имя узла (intake, triage, etc.)
            execution_time_ms: Время выполнения в миллисекундах
            session_id: ID сессии (опционально)
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Записываем общую статистику
            key = self._get_metrics_key(f"execution_time:{node_name}")
            
            # Используем Redis Sorted Set для хранения метрик с временными метками
            timestamp = int(time.time())
            await self.redis_manager.redis_client.zadd(
                key,
                {str(timestamp): execution_time_ms}
            )
            
            # Оставляем только последние 1000 записей
            await self.redis_manager.redis_client.zremrangebyrank(key, 0, -1001)
            
            # Устанавливаем TTL 7 дней
            await self.redis_manager.redis_client.expire(key, 7 * 24 * 3600)
            
            # Записываем метрику для сессии если указана
            if session_id:
                session_key = self._get_metrics_key(f"session:{session_id}:{node_name}")
                await self.redis_manager.redis_client.setex(
                    session_key,
                    24 * 3600,  # TTL 24 часа
                    str(execution_time_ms)
                )
            
            logger.debug(f"Recorded execution time for {node_name}: {execution_time_ms:.2f}ms")
            
        except Exception as e:
            logger.warning(f"Failed to record execution time: {str(e)}")
    
    async def get_node_statistics(self, node_name: str, hours: int = 24) -> Dict[str, Any]:
        """Получение статистики для узла
        
        Args:
            node_name: Имя узла
            hours: Количество часов для анализа
            
        Returns:
            Словарь со статистикой: count, avg, min, max, p50, p95, p99
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            key = self._get_metrics_key(f"execution_time:{node_name}")
            cutoff_time = int(time.time()) - (hours * 3600)
            
            # Получаем все значения за указанный период
            values = await self.redis_manager.redis_client.zrangebyscore(
                key,
                min=cutoff_time,
                max=int(time.time()),
                withscores=False
            )
            
            if not values:
                return {
                    "count": 0,
                    "avg": 0,
                    "min": 0,
                    "max": 0,
                    "p50": 0,
                    "p95": 0,
                    "p99": 0
                }
            
            # Преобразуем в числа и сортируем
            times = sorted([float(v) for v in values])
            count = len(times)
            
            # Вычисляем статистику
            avg = sum(times) / count
            min_time = times[0]
            max_time = times[-1]
            p50 = times[int(count * 0.5)] if count > 0 else 0
            p95 = times[int(count * 0.95)] if count > 1 else times[-1]
            p99 = times[int(count * 0.99)] if count > 1 else times[-1]
            
            return {
                "count": count,
                "avg": round(avg, 2),
                "min": round(min_time, 2),
                "max": round(max_time, 2),
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2)
            }
            
        except Exception as e:
            logger.error(f"Failed to get node statistics: {str(e)}")
            return {
                "count": 0,
                "avg": 0,
                "min": 0,
                "max": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0
            }
    
    async def get_chain_statistics(self, session_id: str) -> Dict[str, Any]:
        """Получение статистики для всей цепочки сессии
        
        Args:
            session_id: ID сессии
            
        Returns:
            Словарь со статистикой по каждому узлу
        """
        if not self._initialized:
            await self.initialize()
        
        nodes = ["intake", "data_completeness_checker", "triage", "hypothesis_generator",
                 "infection", "immune", "oncology", "rare_disease", "synthesis"]
        
        chain_stats = {}
        total_time = 0
        
        for node_name in nodes:
            session_key = self._get_metrics_key(f"session:{session_id}:{node_name}")
            time_str = await self.redis_manager.redis_client.get(session_key)
            
            if time_str:
                node_time = float(time_str)
                chain_stats[node_name] = node_time
                total_time += node_time
        
        chain_stats["total"] = round(total_time, 2)
        return chain_stats


# Глобальный экземпляр метрик
_performance_metrics: Optional[PerformanceMetrics] = None


async def get_performance_metrics() -> PerformanceMetrics:
    """Получение экземпляра метрик производительности"""
    global _performance_metrics
    
    if _performance_metrics is None:
        _performance_metrics = PerformanceMetrics()
        await _performance_metrics.initialize()
    
    return _performance_metrics


def timing_decorator(node_name: str):
    """Декоратор для измерения времени выполнения узла
    
    Args:
        node_name: Имя узла для логирования
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            session_id = None
            
            # Пытаемся извлечь session_id из аргументов
            if args and isinstance(args[0], dict):
                state = args[0]
                session_id = state.get("session_id")
            
            try:
                result = await func(*args, **kwargs)
                execution_time_ms = (time.time() - start_time) * 1000
                
                # Записываем метрику
                metrics = await get_performance_metrics()
                await metrics.record_execution_time(node_name, execution_time_ms, session_id)
                
                # Логируем если время превышает порог
                threshold_ms = {
                    "intake": 5000,
                    "triage": 3000,
                    "hypothesis_generator": 5000,
                    "infection": 10000,
                    "immune": 10000,
                    "oncology": 10000,
                    "rare_disease": 10000,
                    "synthesis": 10000
                }.get(node_name, 5000)
                
                if execution_time_ms > threshold_ms:
                    logger.warning(
                        f"Node {node_name} execution time ({execution_time_ms:.2f}ms) "
                        f"exceeded threshold ({threshold_ms}ms)"
                    )
                
                return result
                
            except Exception as e:
                execution_time_ms = (time.time() - start_time) * 1000
                logger.error(f"Node {node_name} failed after {execution_time_ms:.2f}ms: {str(e)}")
                raise
        
        return wrapper
    return decorator
