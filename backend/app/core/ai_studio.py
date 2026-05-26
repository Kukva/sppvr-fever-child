"""Клиент для взаимодействия с Yandex AI Studio"""

import httpx
import json
import re
import asyncio
import time
from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import datetime
import logging
import openai

from app.config import settings, REGISTERED_AGENT_NAMES
from app.core.state import AgentOutput

logger = logging.getLogger(__name__)


class YandexAIStudioError(Exception):
    """Базовое исключение для Yandex AI Studio"""
    pass


class RateLimitError(YandexAIStudioError):
    """Ошибка превышения rate limit"""
    pass


class AuthenticationError(YandexAIStudioError):
    """Ошибка аутентификации"""
    pass


class CircuitBreaker:
    """Circuit breaker для защиты от каскадных сбоев"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
    
    def record_success(self):
        """Запись успешного запроса"""
        self.failure_count = 0
        self.state = "closed"
    
    def record_failure(self):
        """Запись неудачного запроса"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def can_attempt(self) -> bool:
        """Проверка возможности выполнения запроса"""
        if self.state == "closed":
            return True
        
        if self.state == "open":
            # Проверяем, прошло ли достаточно времени для попытки восстановления
            if self.last_failure_time and (time.time() - self.last_failure_time) >= self.timeout:
                self.state = "half_open"
                logger.info("Circuit breaker entering half-open state")
                return True
            return False
        
        # half_open - разрешаем одну попытку
        return True


class YandexAIStudioClient:
    """Клиент для взаимодействия с моноагентами AI Studio через OpenAI API"""
    
    def __init__(self):
        self.api_key = settings.yandex_api_key
        self.folder_id = settings.yandex_folder_id
        self.base_url = "https://llm.api.cloud.yandex.net/v1"  # OpenAI совместимый endpoint
        
        # OpenAI клиент для Yandex AI Studio
        self.openai_client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Circuit breaker для защиты от каскадных сбоев
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        
        # Redis клиент для кэширования (инициализируется при необходимости)
        self._redis_client = None
        
        # Промпты агентов: из скиллов (SKILL.md) с fallback на встроенные
        self.agent_prompts = self._load_agent_prompts()
    
    async def _get_redis_client(self):
        """Получение Redis клиента для кэширования"""
        if self._redis_client is None:
            try:
                from app.core.redis_client import get_redis_manager
                redis_manager = await get_redis_manager()
                self._redis_client = redis_manager.redis_client
            except Exception as e:
                logger.warning(f"Redis client not available for caching: {str(e)}")
        return self._redis_client
    
    def _get_cache_key(self, agent_name: str, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Генерация ключа кэша на основе агента, промпта и контекста
        
        Args:
            agent_name: Имя агента
            prompt: Промпт пользователя
            context: Контекст с данными пациента
            
        Returns:
            Ключ кэша в формате fever_routing:ai_cache:{agent_name}:{hash}
        """
        import hashlib
        import json
        
        # Включаем в ключ кэша данные пациента из контекста
        context_str = ""
        if context:
            # Извлекаем ключевые данные для кэширования
            patient_data = context.get("patient_data", {})
            # Создаем стабильное представление данных для хэширования
            cache_context = {
                "age_years": patient_data.get("age_years"),
                "age_months": patient_data.get("age_months"),
                "temperature_current": patient_data.get("temperature_current"),
                "duration_days": patient_data.get("duration_days"),
                "symptoms": sorted(patient_data.get("symptoms", [])) if isinstance(patient_data.get("symptoms"), list) else patient_data.get("symptoms"),
                "red_flags": sorted(patient_data.get("red_flags", [])) if isinstance(patient_data.get("red_flags"), list) else patient_data.get("red_flags"),
            }
            context_str = json.dumps(cache_context, sort_keys=True, ensure_ascii=False)
        
        cache_data = f"{agent_name}:{prompt}:{context_str}"
        cache_hash = hashlib.md5(cache_data.encode()).hexdigest()
        return f"fever_routing:ai_cache:{agent_name}:{cache_hash}"
    
    def _get_cache_ttl(self, agent_name: str) -> int:
        """Получение TTL для кэша в зависимости от типа агента
        
        Args:
            agent_name: Имя агента
            
        Returns:
            TTL в секундах
        """
        # TTL для разных типов агентов
        ttl_map = {
            "intake": 24 * 3600,  # 24 часа - данные пациента редко меняются
            "data_completeness_checker": 12 * 3600,  # 12 часов
            "triage": 12 * 3600,  # 12 часов
            "hypothesis_generator": 6 * 3600,  # 6 часов
            "infection": 1 * 3600,  # 1 час - специализированные агенты
            "immune": 1 * 3600,
            "oncology": 1 * 3600,
            "rare_disease": 1 * 3600,
            "synthesis": 2 * 3600,  # 2 часа - финальные рекомендации
            "question": 30 * 60,  # 30 минут - вопросы зависят от контекста
        }
        return ttl_map.get(agent_name, 3600)  # По умолчанию 1 час
    
    async def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Получение ответа из кэша с метриками"""
        try:
            redis_client = await self._get_redis_client()
            if redis_client:
                cached = await redis_client.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit for key: {cache_key[:50]}...")
                    # Увеличиваем счетчик cache hits
                    await self._increment_cache_metric("hits")
                    return cached
                else:
                    # Увеличиваем счетчик cache misses
                    await self._increment_cache_metric("misses")
        except Exception as e:
            logger.debug(f"Cache read error: {str(e)}")
            await self._increment_cache_metric("misses")
        return None
    
    async def _increment_cache_metric(self, metric_type: str):
        """Увеличение метрики кэша (hits/misses)"""
        try:
            redis_client = await self._get_redis_client()
            if redis_client:
                metric_key = f"fever_routing:cache_metrics:{metric_type}"
                await redis_client.incr(metric_key)
                # Устанавливаем TTL 24 часа для метрик
                await redis_client.expire(metric_key, 24 * 3600)
        except Exception as e:
            logger.debug(f"Failed to increment cache metric: {str(e)}")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Получение статистики кэша (hit/miss rate)"""
        try:
            redis_client = await self._get_redis_client()
            if not redis_client:
                return {"hits": 0, "misses": 0, "hit_rate": 0.0}
            
            hits_key = "fever_routing:cache_metrics:hits"
            misses_key = "fever_routing:cache_metrics:misses"
            
            hits = await redis_client.get(hits_key)
            misses = await redis_client.get(misses_key)
            
            hits = int(hits) if hits else 0
            misses = int(misses) if misses else 0
            total = hits + misses
            
            hit_rate = (hits / total * 100) if total > 0 else 0.0
            
            return {
                "hits": hits,
                "misses": misses,
                "total": total,
                "hit_rate": round(hit_rate, 2)
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {str(e)}")
            return {"hits": 0, "misses": 0, "hit_rate": 0.0}
    
    async def _set_cached_response(self, cache_key: str, response: str, ttl_seconds: int = 3600):
        """Сохранение ответа в кэш"""
        try:
            redis_client = await self._get_redis_client()
            if redis_client:
                await redis_client.setex(cache_key, ttl_seconds, response)
                logger.debug(f"Cached response for key: {cache_key[:50]}...")
        except Exception as e:
            logger.debug(f"Cache write error: {str(e)}")
    
    def _load_agent_prompts(self) -> Dict[str, str]:
        """Системные промпты только из Agent Skills (backend/skills/<agent>/SKILL.md)."""
        from app.core.skills_loader import get_instructions_for_agent

        minimal_fallback = (
            "Ты — ассистент клинической поддержки. Следуй запросу пользователя; "
            "если нужен JSON — верни только валидный JSON. "
            "ВНИМАНИЕ: для этого агента не найден файл SKILL.md — добавьте backend/skills/<имя>/SKILL.md."
        )
        result: Dict[str, str] = {}
        for agent_name in REGISTERED_AGENT_NAMES:
            loaded = get_instructions_for_agent(agent_name)
            if loaded and loaded.strip():
                result[agent_name] = loaded
            else:
                logger.error(
                    "Skill missing or empty for agent %s — using minimal fallback. "
                    "Expected: backend/skills/%s/SKILL.md",
                    agent_name,
                    agent_name,
                )
                result[agent_name] = minimal_fallback
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException, openai.APIError))
    )
    async def call_agent(
        self,
        agent_name: str,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4000,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Вызов моноагента через OpenAI-совместимый API Yandex AI Studio с circuit breaker и кэшированием"""
        
        start_time = time.time()
        
        # Проверка circuit breaker
        if not self.circuit_breaker.can_attempt():
            logger.warning(f"Circuit breaker is open for agent {agent_name}, rejecting request")
            return {
                "error": "Service temporarily unavailable (circuit breaker open)",
                "execution_time_ms": 0,
                "agent_name": agent_name,
                "timestamp": datetime.now().isoformat(),
                "raw_text": None,
                "parsed_data": None,
                "circuit_breaker_open": True
            }
        
        try:
            # Получение конфигурации агента
            agent_config = settings.get_agent_config(agent_name)
            
            # Формирование промпта
            system_prompt = self.agent_prompts.get(agent_name, "")
            user_prompt = self._format_prompt(prompt, context)
            
            # Проверка кэша (с учетом промпта и контекста)
            if use_cache:
                cache_key = self._get_cache_key(agent_name, user_prompt, context)
                cached_response = await self._get_cached_response(cache_key)
                if cached_response:
                    logger.info(f"Cache hit for agent {agent_name} (key: {cache_key[:50]}...)")
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    return {
                        "raw_text": cached_response,
                        "parsed_data": self._extract_json_from_text(cached_response),
                        "success": True,
                        "execution_time_ms": execution_time_ms,
                        "agent_name": agent_name,
                        "timestamp": datetime.now().isoformat(),
                        "cached": True
                    }
            
            # Формирование сообщений для OpenAI API
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
            
            logger.info(f"Calling agent {agent_name} with prompt length: {len(user_prompt)}")
            
            # Вызов через OpenAI API с таймаутом
            response = self.openai_client.chat.completions.create(
                model=agent_config["model_uri"],
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
                timeout=30.0  # Таймаут 30 секунд
            )
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Извлечение текста ответа
            text = response.choices[0].message.content or ""
            
            # Сохранение в кэш
            if use_cache and text:
                cache_key = self._get_cache_key(agent_name, user_prompt, context)
                ttl_seconds = self._get_cache_ttl(agent_name)
                await self._set_cached_response(cache_key, text, ttl_seconds=ttl_seconds)
                logger.debug(f"Cached response for agent {agent_name} with TTL {ttl_seconds}s")
            
            # Парсинг ответа
            parsed_result = self._parse_agent_response(agent_name, {"text": text})
            
            # Запись успеха в circuit breaker
            self.circuit_breaker.record_success()
            
            logger.info(f"Agent {agent_name} completed in {execution_time_ms}ms")
            
            return {
                **parsed_result,
                "execution_time_ms": execution_time_ms,
                "agent_name": agent_name,
                "timestamp": datetime.now().isoformat(),
                "cached": False
            }
            
        except openai.AuthenticationError as e:
            self.circuit_breaker.record_failure()
            raise AuthenticationError(f"Invalid API key or folder ID: {str(e)}")
        except openai.RateLimitError as e:
            self.circuit_breaker.record_failure()
            raise RateLimitError(f"Rate limit exceeded: {str(e)}")
        except openai.APIError as e:
            self.circuit_breaker.record_failure()
            raise YandexAIStudioError(f"API error: {str(e)}")
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Agent {agent_name} failed after {execution_time_ms}ms: {str(e)}")
            
            # Запись ошибки в circuit breaker
            self.circuit_breaker.record_failure()
            
            # Возврат ошибки в стандартизированном формате
            return {
                "error": str(e),
                "execution_time_ms": execution_time_ms,
                "agent_name": agent_name,
                "timestamp": datetime.now().isoformat(),
                "raw_text": None,
                "parsed_data": None
            }
    
    def _format_prompt(self, prompt: str, context: Optional[Dict[str, Any]]) -> str:
        """Форматирование промпта с контекстом"""
        if context:
            context_str = "\n".join([f"{k}: {json.dumps(v, ensure_ascii=False, indent=2)}" for k, v in context.items()])
            return f"{context_str}\n\n{prompt}"
        return prompt
    
    def _parse_agent_response(self, agent_name: str, response: Dict[str, Any]) -> Dict[str, Any]:
        """Парсинг ответа агента"""
        
        try:
            # Извлечение текста ответа (новый формат от OpenAI API)
            text = response.get("text", "")
            
            # Попытка распарсить JSON из ответа
            parsed_data = self._extract_json_from_text(text)
            
            if parsed_data:
                return {
                    "raw_text": text,
                    "parsed_data": parsed_data,
                    "success": True
                }
            else:
                # Если JSON не найден, возвращаем сырой текст
                return {
                    "raw_text": text,
                    "parsed_data": None,
                    "success": False,
                    "warning": "No JSON found in response"
                }
                
        except Exception as e:
            logger.error(f"Failed to parse agent response: {str(e)}")
            return {
                "raw_text": str(response),
                "parsed_data": None,
                "success": False,
                "error": str(e)
            }
    
    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Извлечение JSON из текста ответа"""
        
        try:
            # Поиск JSON в тексте
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            
            # Поиск JSON в кодовых блоках
            code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if code_block_match:
                json_str = code_block_match.group(1)
                return json.loads(json_str)
            
            return None
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode JSON: {str(e)}")
            return None
    
    async def close(self):
        """Закрытие клиента"""
        # OpenAI клиент не требует явного закрытия
        pass
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Глобальный экземпляр клиента
_ai_studio_client: Optional[YandexAIStudioClient] = None


async def get_ai_studio_client() -> YandexAIStudioClient:
    """Получение экземпляра клиента AI Studio"""
    global _ai_studio_client
    
    if _ai_studio_client is None:
        _ai_studio_client = YandexAIStudioClient()
    
    return _ai_studio_client


async def close_ai_studio_client():
    """Закрытие клиента AI Studio"""
    global _ai_studio_client
    
    if _ai_studio_client is not None:
        await _ai_studio_client.close()
        _ai_studio_client = None