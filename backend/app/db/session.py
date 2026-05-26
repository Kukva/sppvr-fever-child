"""Сессии базы данных и инициализация"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.config import settings
from app.db.models import Base

# Асинхронный движок
async_engine = create_async_engine(
    settings.database_url_async,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=20,
    max_overflow=30
)

# Синхронный движок (для миграций и checkpointer)
sync_engine = create_async_engine(
    settings.database_url_sync.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=20,
    max_overflow=30
)

# Фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Синхронная фабрика сессий
SessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)


async def get_db():
    """Получение асинхронной сессии базы данных"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_db_session():
    """Получение асинхронной сессии для использования с async with"""
    return AsyncSessionLocal()


def get_sync_db():
    """Получение синхронной сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def init_db():
    """Инициализация базы данных"""
    try:
        # Создание всех таблиц
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database tables created successfully")
        
        # Создание таблиц для LangGraph checkpointer
        await create_langgraph_tables()
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise


async def create_langgraph_tables():
    """Создание таблиц для LangGraph checkpointer"""
    
    # SQL для создания таблиц checkpointer
    checkpoint_table_sql = """
    CREATE TABLE IF NOT EXISTS checkpoints (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        parent_checkpoint_id TEXT,
        type TEXT,
        checkpoint JSONB NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
    );
    """
    
    checkpoint_writes_table_sql = """
    CREATE TABLE IF NOT EXISTS checkpoint_writes (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        idx INTEGER NOT NULL,
        channel TEXT NOT NULL,
        type TEXT,
        value JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
    );
    """
    
    # Создание индексов
    checkpoint_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON checkpoints(thread_id);",
        "CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON checkpoints(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread_id ON checkpoint_writes(thread_id);",
        "CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_created_at ON checkpoint_writes(created_at);"
    ]
    
    try:
        async with async_engine.begin() as conn:
            # Создание таблиц
            await conn.execute(text(checkpoint_table_sql))
            await conn.execute(text(checkpoint_writes_table_sql))
            
            # Создание индексов
            for index_sql in checkpoint_indexes_sql:
                await conn.execute(text(index_sql))
        
        logger.info("LangGraph checkpoint tables created successfully")
        
    except Exception as e:
        logger.error(f"Failed to create LangGraph tables: {str(e)}")
        raise


async def close_db():
    """Закрытие соединений с базой данных"""
    await async_engine.dispose()
    await sync_engine.dispose()


# Импорт логгера
import logging
logger = logging.getLogger(__name__)