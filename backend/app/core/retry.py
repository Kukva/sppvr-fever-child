"""Модуль для retry механизма с экспоненциальной задержкой"""

import asyncio
import logging
from typing import Callable, TypeVar, Optional, List, Any
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryPolicy:
    """Политика повторных попыток с экспоненциальной задержкой"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 10.0,
        exponential_base: float = 2.0,
        retryable_exceptions: Optional[List[type]] = None
    ):
        """
        Args:
            max_attempts: Максимальное количество попыток
            initial_delay: Начальная задержка в секундах
            max_delay: Максимальная задержка в секундах
            exponential_base: База для экспоненциальной задержки
            retryable_exceptions: Список исключений, при которых нужно повторять попытку
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions or [Exception]
    
    def _calculate_delay(self, attempt: int) -> float:
        """Вычисление задержки для попытки"""
        delay = self.initial_delay * (self.exponential_base ** (attempt - 1))
        return min(delay, self.max_delay)
    
    async def execute(
        self,
        func: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """Выполнение функции с retry механизмом
        
        Args:
            func: Асинхронная функция для выполнения
            *args: Позиционные аргументы
            **kwargs: Именованные аргументы
            
        Returns:
            Результат выполнения функции
            
        Raises:
            Последнее исключение, если все попытки исчерпаны
        """
        last_exception = None
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                if attempt > 1:
                    logger.info(f"Function {func.__name__} succeeded on attempt {attempt}")
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Проверяем, нужно ли повторять попытку
                if not any(isinstance(e, exc_type) for exc_type in self.retryable_exceptions):
                    logger.warning(f"Non-retryable exception in {func.__name__}: {type(e).__name__}")
                    raise
                
                if attempt < self.max_attempts:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt}/{self.max_attempts} failed for {func.__name__}: "
                        f"{type(e).__name__}: {str(e)}. Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_attempts} attempts exhausted for {func.__name__}. "
                        f"Last error: {type(e).__name__}: {str(e)}"
                    )
        
        # Все попытки исчерпаны
        raise last_exception


# Предустановленные политики retry для разных типов операций
class RetryPolicies:
    """Предустановленные политики retry"""
    
    # Для критических агентов (intake, triage)
    CRITICAL_AGENT = RetryPolicy(
        max_attempts=3,
        initial_delay=1.0,
        max_delay=4.0,
        exponential_base=2.0
    )
    
    # Для специализированных агентов
    SPECIALIST_AGENT = RetryPolicy(
        max_attempts=2,
        initial_delay=1.0,
        max_delay=2.0,
        exponential_base=2.0
    )
    
    # Для внешних API вызовов
    API_CALL = RetryPolicy(
        max_attempts=3,
        initial_delay=0.5,
        max_delay=5.0,
        exponential_base=2.0
    )
    
    # Для операций с базой данных
    DATABASE_OPERATION = RetryPolicy(
        max_attempts=2,
        initial_delay=0.5,
        max_delay=2.0,
        exponential_base=2.0
    )


def retry_on_failure(
    policy: Optional[RetryPolicy] = None,
    retryable_exceptions: Optional[List[type]] = None
):
    """Декоратор для автоматического retry при ошибках
    
    Args:
        policy: Политика retry (по умолчанию используется CRITICAL_AGENT)
        retryable_exceptions: Список исключений для retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            retry_policy = policy or RetryPolicies.CRITICAL_AGENT
            if retryable_exceptions:
                retry_policy.retryable_exceptions = retryable_exceptions
            
            return await retry_policy.execute(func, *args, **kwargs)
        
        return wrapper
    return decorator
