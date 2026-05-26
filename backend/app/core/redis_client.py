"""Redis клиент для хранения состояния сессий"""

import json
import logging
import time
from typing import Optional, Dict, Any
from datetime import timedelta
import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)


class RedisSessionManager:
    """Менеджер сессий в Redis"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._initialized = False
    
    async def initialize(self):
        """Инициализация Redis клиента"""
        if self._initialized:
            return
        
        try:
            # Создаем асинхронный Redis клиент
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            # Проверяем соединение
            await self.redis_client.ping()
            self._initialized = True
            logger.info(f"Redis client initialized: {settings.redis_host}:{settings.redis_port}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {str(e)}")
            raise
    
    async def close(self):
        """Закрытие соединения с Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self._initialized = False
            logger.info("Redis client closed")
    
    def _get_session_key(self, session_id: str) -> str:
        """Получение ключа сессии в Redis"""
        return f"fever_routing:session:{session_id}"
    
    async def save_session_state(
        self, 
        session_id: str, 
        state: Dict[str, Any],
        ttl_hours: int = 24
    ) -> bool:
        """Сохранение состояния сессии в Redis
        
        Args:
            session_id: ID сессии
            state: Состояние графа
            ttl_hours: Время жизни в часах
            
        Returns:
            True если успешно сохранено
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Сериализация состояния
            serialized_state = self._serialize_state(state)
            
            # Сохранение в Redis с TTL
            key = self._get_session_key(session_id)
            await self.redis_client.setex(
                key,
                timedelta(hours=ttl_hours),
                serialized_state
            )
            
            logger.debug(f"Session {session_id} saved to Redis with TTL {ttl_hours}h")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {str(e)}")
            return False
    
    async def load_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Загрузка состояния сессии из Redis
        
        Args:
            session_id: ID сессии
            
        Returns:
            Состояние графа или None если не найдено
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            key = self._get_session_key(session_id)
            serialized_state = await self.redis_client.get(key)
            
            if serialized_state:
                state = self._deserialize_state(serialized_state)
                logger.debug(f"Session {session_id} loaded from Redis")
                return state
            
            logger.debug(f"Session {session_id} not found in Redis")
            return None
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {str(e)}")
            return None
    
    async def delete_session(self, session_id: str) -> bool:
        """Удаление сессии из Redis
        
        Args:
            session_id: ID сессии
            
        Returns:
            True если успешно удалено
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            key = self._get_session_key(session_id)
            result = await self.redis_client.delete(key)
            
            if result:
                logger.debug(f"Session {session_id} deleted from Redis")
                return True
            
            logger.debug(f"Session {session_id} not found for deletion")
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {str(e)}")
            return False
    
    async def session_exists(self, session_id: str) -> bool:
        """Проверка существования сессии
        
        Args:
            session_id: ID сессии
            
        Returns:
            True если сессия существует
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            key = self._get_session_key(session_id)
            exists = await self.redis_client.exists(key)
            return bool(exists)
            
        except Exception as e:
            logger.error(f"Failed to check session {session_id}: {str(e)}")
            return False
    
    async def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Получение всех активных сессий
        
        Returns:
            Словарь {session_id: state}
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            pattern = f"{self._get_session_key('')}"
            pattern = pattern.rstrip(':') + ":*"
            
            keys = await self.redis_client.keys(pattern)
            sessions = {}
            
            for key in keys:
                # Извлекаем session_id из ключа
                session_id = key.split(':')[-1]
                serialized_state = await self.redis_client.get(key)
                
                if serialized_state:
                    state = self._deserialize_state(serialized_state)
                    sessions[session_id] = state
            
            logger.info(f"Loaded {len(sessions)} sessions from Redis")
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get all sessions: {str(e)}")
            return {}
    
    def _serialize_state(self, state: Dict[str, Any]) -> str:
        """Сериализация состояния в JSON
        
        Args:
            state: Состояние графа
            
        Returns:
            JSON строка
        """
        # Обработка специальных объектов
        serializable_state = {}
        
        for key, value in state.items():
            if key == "urgency_level" and hasattr(value, 'value'):
                # Enum для UrgencyLevel
                serializable_state[key] = value.value
            elif isinstance(value, (list, dict, str, int, float, bool, type(None))):
                # Простые типы
                serializable_state[key] = value
            else:
                # Для остальных объектов пытаемся преобразовать в строку
                serializable_state[key] = str(value)
        
        return json.dumps(serializable_state, ensure_ascii=False, default=str)
    
    def _deserialize_state(self, serialized_state: str) -> Dict[str, Any]:
        """Десериализация состояния из JSON
        
        Args:
            serialized_state: JSON строка
            
        Returns:
            Состояние графа
        """
        state = json.loads(serialized_state)
        
        # Восстановление специальных объектов
        if "urgency_level" in state and state["urgency_level"]:
            from app.core.state import UrgencyLevel
            try:
                state["urgency_level"] = UrgencyLevel(state["urgency_level"])
            except ValueError:
                logger.warning(f"Invalid urgency_level: {state['urgency_level']}")
                state["urgency_level"] = None
        
        return state
    
    def _get_cache_key(self, key: str) -> str:
        """Получение ключа кэша в Redis"""
        return f"fever_routing:cache:{key}"
    
    async def cache_set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 3600
    ) -> bool:
        """Сохранение значения в кэш
        
        Args:
            key: Ключ кэша
            value: Значение для кэширования (будет сериализовано в JSON)
            ttl_seconds: Время жизни в секундах
            
        Returns:
            True если успешно сохранено
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            cache_key = self._get_cache_key(key)
            # Сериализация значения
            if isinstance(value, str):
                serialized_value = value
            else:
                serialized_value = json.dumps(value, ensure_ascii=False, default=str)
            
            await self.redis_client.setex(
                cache_key,
                ttl_seconds,
                serialized_value
            )
            
            logger.debug(f"Cached value for key: {key[:50]}... (TTL: {ttl_seconds}s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache value for key {key}: {str(e)}")
            return False
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """Получение значения из кэша
        
        Args:
            key: Ключ кэша
            
        Returns:
            Значение из кэша или None если не найдено
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            cache_key = self._get_cache_key(key)
            cached_value = await self.redis_client.get(cache_key)
            
            if cached_value:
                # Пытаемся десериализовать JSON, если не получается - возвращаем как строку
                try:
                    return json.loads(cached_value)
                except (json.JSONDecodeError, TypeError):
                    return cached_value
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cached value for key {key}: {str(e)}")
            return None
    
    async def cache_delete(self, key: str) -> bool:
        """Удаление значения из кэша
        
        Args:
            key: Ключ кэша
            
        Returns:
            True если успешно удалено
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            cache_key = self._get_cache_key(key)
            result = await self.redis_client.delete(cache_key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to delete cached value for key {key}: {str(e)}")
            return False
    
    async def cache_invalidate_pattern(self, pattern: str) -> int:
        """Инвалидация кэша по паттерну
        
        Args:
            pattern: Паттерн для поиска ключей (например, "agent_cache:intake:*")
            
        Returns:
            Количество удаленных ключей
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Добавляем префикс к паттерну
            full_pattern = f"fever_routing:cache:{pattern}"
            keys = await self.redis_client.keys(full_pattern)
            
            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries matching pattern: {pattern}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache pattern {pattern}: {str(e)}")
            return 0


# Глобальный экземпляр менеджера сессий
_redis_manager: Optional[RedisSessionManager] = None


async def get_redis_manager() -> RedisSessionManager:
    """Получение экземпляра менеджера Redis"""
    global _redis_manager
    
    if _redis_manager is None:
        _redis_manager = RedisSessionManager()
        await _redis_manager.initialize()
    
    return _redis_manager


class RedisRateLimiter:
    """Rate limiter на базе Redis для масштабируемости и персистентности"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._initialized = False
    
    async def initialize(self):
        """Инициализация Redis клиента"""
        if self._initialized:
            return
        
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            await self.redis_client.ping()
            self._initialized = True
            logger.info(f"Redis RateLimiter initialized: {settings.redis_host}:{settings.redis_port}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis RateLimiter: {str(e)}")
            raise
    
    async def close(self):
        """Закрытие соединения с Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self._initialized = False
            logger.info("Redis RateLimiter closed")
    
    def _get_rate_limit_key(self, identifier: str, window: str) -> str:
        """Получение ключа для rate limiting"""
        return f"fever_routing:ratelimit:{window}:{identifier}"
    
    async def check_rate_limit(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int, int]:
        """Проверка rate limit
        
        Args:
            identifier: Уникальный идентификатор (session_id, IP и т.д.)
            max_requests: Максимальное количество запросов
            window_seconds: Окно времени в секундах
            
        Returns:
            Tuple (is_allowed, remaining, reset_time)
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            key = self._get_rate_limit_key(identifier, f"{window_seconds}s")
            current_time = int(time.time())
            
            # Используем транзакцию для атомарности
            pipe = self.redis_client.pipeline()
            
            # Удаляем старые записи (старше window_seconds)
            pipe.zremrangebyscore(key, 0, current_time - window_seconds)
            
            # Подсчитываем текущие запросы
            pipe.zcard(key)
            
            # Добавляем текущий запрос
            pipe.zadd(key, {str(current_time): current_time})
            
            # Устанавливаем TTL для автоматической очистки
            pipe.expire(key, window_seconds + 60)  # +60 секунд для безопасности
            
            results = await pipe.execute()
            current_count = results[1]
            
            # Проверяем лимит
            if current_count >= max_requests:
                # Получаем время самого старого запроса для расчета reset_time
                oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_time = int(oldest[0][1]) + window_seconds
                else:
                    reset_time = current_time + window_seconds
                
                return False, 0, reset_time
            
            # Увеличиваем счетчик после добавления
            remaining = max(0, max_requests - current_count - 1)
            reset_time = current_time + window_seconds
            
            return True, remaining, reset_time
            
        except Exception as e:
            logger.error(f"Rate limit check failed for {identifier}: {str(e)}")
            # В случае ошибки Redis разрешаем запрос (fail-open)
            return True, max_requests, int(time.time()) + window_seconds
    
    async def increment_rate_limit(
        self,
        identifier: str,
        window_seconds: int
    ):
        """Увеличение счетчика rate limit"""
        if not self._initialized:
            await self.initialize()
        
        try:
            key = self._get_rate_limit_key(identifier, f"{window_seconds}s")
            current_time = int(time.time())
            
            await self.redis_client.zadd(key, {str(current_time): current_time})
            await self.redis_client.expire(key, window_seconds + 60)
            
        except Exception as e:
            logger.error(f"Rate limit increment failed for {identifier}: {str(e)}")
    
    async def get_rate_limit_status(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> dict:
        """Получение текущего статуса rate limit"""
        if not self._initialized:
            await self.initialize()
        
        try:
            key = self._get_rate_limit_key(identifier, f"{window_seconds}s")
            current_time = int(time.time())
            
            # Удаляем старые записи
            await self.redis_client.zremrangebyscore(key, 0, current_time - window_seconds)
            
            # Подсчитываем текущие запросы
            current_count = await self.redis_client.zcard(key)
            remaining = max(0, max_requests - current_count)
            
            # Получаем время самого старого запроса
            oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
            if oldest:
                reset_time = int(oldest[0][1]) + window_seconds
            else:
                reset_time = current_time + window_seconds
            
            return {
                "limit": max_requests,
                "remaining": remaining,
                "reset_time": reset_time,
                "current_count": current_count
            }
            
        except Exception as e:
            logger.error(f"Rate limit status failed for {identifier}: {str(e)}")
            return {
                "limit": max_requests,
                "remaining": max_requests,
                "reset_time": int(time.time()) + window_seconds,
                "current_count": 0
            }
    
    async def cleanup_old_entries(self, max_age_seconds: int = 3600):
        """Очистка старых записей rate limiting"""
        if not self._initialized:
            await self.initialize()
        
        try:
            pattern = "fever_routing:ratelimit:*"
            keys = await self.redis_client.keys(pattern)
            current_time = int(time.time())
            cleaned = 0
            
            for key in keys:
                # Проверяем TTL ключа
                ttl = await self.redis_client.ttl(key)
                if ttl == -1:  # Ключ без TTL - устанавливаем
                    await self.redis_client.expire(key, max_age_seconds)
                elif ttl < 0:  # Ключ не существует
                    continue
                
                # Удаляем старые записи
                removed = await self.redis_client.zremrangebyscore(
                    key, 0, current_time - max_age_seconds
                )
                if removed > 0:
                    cleaned += removed
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} old rate limit entries")
            
        except Exception as e:
            logger.error(f"Rate limit cleanup failed: {str(e)}")


# Глобальный экземпляр rate limiter
_rate_limiter: Optional[RedisRateLimiter] = None


async def get_rate_limiter() -> RedisRateLimiter:
    """Получение экземпляра rate limiter"""
    global _rate_limiter
    
    if _rate_limiter is None:
        _rate_limiter = RedisRateLimiter()
        await _rate_limiter.initialize()
    
    return _rate_limiter