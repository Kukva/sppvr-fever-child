"""Конфигурация приложения"""

import os
from typing import Optional
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


class Settings:
    """Настройки приложения"""
    
    def __init__(self):
        # Application
        self.app_name = "Fever Routing System"
        self.app_version = "1.0.0"
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        
        # Database
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = int(os.getenv("DB_PORT", "5432"))
        self.db_name = os.getenv("DB_NAME", "fever_routing")
        self.db_user = os.getenv("DB_USER", "fever_user")
        self.db_password = os.getenv("DB_PASSWORD", "secure_password_change_me")
        
        # Redis
        # Парсим REDIS_URL если он задан, иначе используем отдельные переменные
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            # Парсим URL вида redis://host:port/db
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            self.redis_host = parsed.hostname or "localhost"
            self.redis_port = parsed.port or 6379
            # Извлекаем номер БД из пути (например, /0)
            self.redis_db = int(parsed.path.lstrip('/')) if parsed.path and parsed.path != '/' else 0
        else:
            self.redis_host = os.getenv("REDIS_HOST", "localhost")
            self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
            self.redis_db = int(os.getenv("REDIS_DB", "0"))
        
        # Yandex AI Studio
        self.yandex_api_key = os.getenv("YANDEX_CLOUD_API_KEY", "")
        self.yandex_folder_id = os.getenv("YANDEX_CLOUD_FOLDER_ID", "")
        self.yandex_model_uri = f"gpt://{self.yandex_folder_id}/yandexgpt/latest"
        
        # Agent IDs (Yandex AI Studio prompt IDs для Responses API, см. backend/docs/YANDEX_AI_AGENTS.md)
        self.intake_agent_id = "YOUR_INTAKE_AGENT_ID"
        self.data_completeness_checker_agent_id = "YOUR_DATA_COMPLETENESS_AGENT_ID"
        self.triage_agent_id = "YOUR_TRIAGE_AGENT_ID"
        self.hypothesis_generator_agent_id = "YOUR_HYPOTHESIS_AGENT_ID"
        self.infection_agent_id = "YOUR_INFECTION_AGENT_ID"
        self.immune_agent_id = "YOUR_IMMUNE_AGENT_ID"
        self.oncology_agent_id = "YOUR_ONCOLOGY_AGENT_ID"
        self.rare_disease_agent_id = "YOUR_RARE_DISEASE_AGENT_ID"
        self.question_agent_id = "YOUR_QUESTION_AGENT_ID"
        self.synthesis_agent_id = "YOUR_SYNTHESIS_AGENT_ID"
        
        # API
        self.api_host = "0.0.0.0"
        self.api_port = int(os.getenv("API_PORT", "8000"))
        # CORS: разрешаем конкретные домены или все в development
        cors_origins_env = os.getenv("CORS_ORIGINS", "").strip()
        if cors_origins_env:
            # Поддержка формата "url1,url2" или ["url1","url2"]
            if cors_origins_env.startswith("["):
                import json
                try:
                    self.cors_origins = json.loads(cors_origins_env)
                except json.JSONDecodeError:
                    self.cors_origins = [o.strip().strip('"') for o in cors_origins_env.strip("[]").split(",")]
            else:
                self.cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]
            self.cors_origins = [o for o in self.cors_origins if o]
        elif self.debug:
            # В debug режиме разрешаем все
            self.cors_origins = ["*"]
        else:
            # В production по умолчанию только localhost (для безопасности)
            self.cors_origins = [
                "http://localhost:3000",
                "http://localhost:80",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:80",
            ]
        # Всегда добавляем localhost:3000 для надёжности при работе с браузером
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            if origin not in self.cors_origins and "*" not in self.cors_origins:
                self.cors_origins.append(origin)
        
        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_file = "logs/app.log"
        
        # File Storage (PDF_EXPORT_DIR: в Docker лучше оставить exports/pdf; при 502 из-за прав — задать /tmp/pdf-exports)
        self.pdf_export_dir = os.getenv("PDF_EXPORT_DIR", "exports/pdf")
        self.max_file_size_mb = 10
        
        # Monitoring
        self.prometheus_port = 8001
        self.enable_metrics = True
        
        # LangSmith (опционально)
        self.langchain_tracing_v2 = False
        self.langchain_api_key = os.getenv("LANGCHAIN_API_KEY")
        self.langchain_project = "fever-routing-system"
        
        # Rate Limiting
        self.rate_limit_per_minute = 60
        self.rate_limit_per_hour = 1000
        
        # Session
        self.session_timeout_minutes = 60
        self.max_session_duration_hours = 24

        # Run mode (MAI-DxO-подобные режимы: full, instant, question_only, budgeted)
        self.run_mode = os.getenv("RUN_MODE", "full").lower()
        self.max_cost_units = int(os.getenv("MAX_COST_UNITS", "0")) or None  # 0 = без лимита
        self.enable_clinical_eval = os.getenv("ENABLE_CLINICAL_EVAL", "false").lower() == "true"

        # LangGraph: лимит шагов (см. GraphRecursionError при зацикливании маршрутизации)
        self.graph_recursion_limit = int(os.getenv("GRAPH_RECURSION_LIMIT", "50"))

        # Environment variables
        self.database_url = os.getenv("DATABASE_URL", "")
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.secret_key = os.getenv("SECRET_KEY", "")
        
        # Валидация обязательных переменных окружения
        self._validate_required_settings()
    
    @property
    def database_url_sync(self) -> str:
        """Синхронный URL для PostgreSQL"""
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def database_url_async(self) -> str:
        """Асинхронный URL для PostgreSQL"""
        if self.database_url:
            # Заменяем postgresql:// на postgresql+asyncpg://
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def yandex_api_base_url(self) -> str:
        """Базовый URL Yandex AI Studio API"""
        return "https://llm.api.cloud.yandex.net/foundationModels/v1"
    
    def _validate_required_settings(self):
        """Валидация обязательных настроек при старте"""
        import logging
        logger = logging.getLogger(__name__)
        
        errors = []
        warnings = []
        
        # Критически важные настройки для production
        if not self.debug:
            if not self.yandex_api_key:
                errors.append("YANDEX_CLOUD_API_KEY не установлен")
            if not self.yandex_folder_id:
                errors.append("YANDEX_CLOUD_FOLDER_ID не установлен")
            if not self.secret_key:
                errors.append("SECRET_KEY не установлен (критично для безопасности)")
            if self.cors_origins == ["*"]:
                warnings.append("CORS разрешает все источники (*) - небезопасно для production")
        
        # Предупреждения для development
        if self.debug:
            if not self.yandex_api_key:
                warnings.append("YANDEX_CLOUD_API_KEY не установлен - AI функции не будут работать")
            if not self.yandex_folder_id:
                warnings.append("YANDEX_CLOUD_FOLDER_ID не установлен - AI функции не будут работать")
        
        # Вывод ошибок и предупреждений
        if errors:
            error_msg = "Критические ошибки конфигурации:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if warnings:
            warning_msg = "Предупреждения конфигурации:\n" + "\n".join(f"  - {w}" for w in warnings)
            logger.warning(warning_msg)
    
    def get_agent_config(self, agent_name: str) -> dict:
        """Получить конфигурацию агента по имени"""
        agent_configs = {
            "intake": {
                "agent_id": self.intake_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "data_completeness_checker": {
                "agent_id": self.data_completeness_checker_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "triage": {
                "agent_id": self.triage_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "hypothesis_generator": {
                "agent_id": self.hypothesis_generator_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "infection": {
                "agent_id": self.infection_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "immune": {
                "agent_id": self.immune_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "oncology": {
                "agent_id": self.oncology_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "rare_disease": {
                "agent_id": self.rare_disease_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "question": {
                "agent_id": self.question_agent_id,
                "model_uri": self.yandex_model_uri
            },
            "synthesis": {
                "agent_id": self.synthesis_agent_id,
                "model_uri": self.yandex_model_uri
            }
        }
        
        config = agent_configs.get(agent_name)
        if not config:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        return config


# Имена агентов графа (совпадают с каталогами backend/skills/<name>/)
REGISTERED_AGENT_NAMES = (
    "intake",
    "data_completeness_checker",
    "triage",
    "hypothesis_generator",
    "infection",
    "immune",
    "oncology",
    "rare_disease",
    "question",
    "synthesis",
)


# Глобальный экземпляр настроек
settings = Settings()

# Создание необходимых директорий (при ошибке прав — только предупреждение, чтобы контейнер стартовал)
def _ensure_dirs():
    import logging
    _log = logging.getLogger(__name__)
    for d in (settings.pdf_export_dir, "logs"):
        try:
            os.makedirs(d, exist_ok=True)
        except (PermissionError, OSError) as e:
            _log.warning("Не удалось создать директорию %s: %s (PDF/логи могут быть недоступны)", d, e)

_ensure_dirs()