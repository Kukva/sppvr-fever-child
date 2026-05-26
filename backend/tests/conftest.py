"""Конфигурация pytest для тестирования"""

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.state import GraphState, PatientData
from typing import TypedDict

# Backward compatibility: ChatState and TriageResult (if not in state)
ChatState = GraphState


class TriageResult(TypedDict, total=False):
    urgency_level: str
    fever_classification: str
    activate_agents: list
    reasoning: str
    immediate_actions: list


from app.db.models import Base
from app.db.session import get_db
from app.config import settings


# Тестовая база данных (движок создаётся лениво, чтобы не падать при отсутствии aiosqlite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
test_engine = None
TestSessionLocal = None


def _get_test_engine():
    global test_engine, TestSessionLocal
    if test_engine is None:
        test_engine = create_async_engine(
            TEST_DATABASE_URL,
            echo=False,
            future=True,
        )
        TestSessionLocal = sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )
    return test_engine, TestSessionLocal


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Создание event loop для асинхронных тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Создание тестовой сессии базы данных"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        yield session
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Создание тестового клиента"""
    
    def override_get_db():
        return db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_patient_data() -> dict:
    """Пример данных пациента для тестов"""
    return {
        "raw_input": "Ребенок 5 лет, температура 39.2°C уже 3 дня. Кашель, насморк, отказывается есть. Был контакт с больным ОРВИ."
    }


@pytest.fixture
def structured_patient_data() -> PatientData:
    """Структурированные данные пациента"""
    return PatientData(
        age_years=5,
        age_months=0,
        temperature_current=39.2,
        temperature_max=39.2,
        temperature_pattern="постоянная",
        duration_days=3,
        symptoms=["кашель", "насморк", "отказ от еды"],
        red_flags=["отказ от еды"],
        anamnesis={},
        physical_exam={},
        lab_results={},
        missing_info=[],
    )


@pytest.fixture
def triage_result() -> TriageResult:
    """Результат триажа"""
    return TriageResult(
        urgency_level="urgent",
        fever_classification="без очага",
        activate_agents=["INFECTION", "IMMUNE"],
        reasoning="Лихорадка >3 дней без явного очага инфекции",
        immediate_actions=["Сбор анализов", "Консультация специалиста"]
    )


@pytest.fixture
def chat_state(structured_patient_data: PatientData, triage_result: TriageResult) -> ChatState:
    """Состояние чата для тестов"""
    return ChatState(
        session_id="test_session_123",
        messages=[
            {"role": "user", "content": "Ребенок 5 лет, температура 39.2°C уже 3 дня"}
        ],
        patient_data=structured_patient_data,
        triage_result=triage_result,
        current_step="synthesis",
        is_complete=False,
        metadata={"test_mode": True}
    )


@pytest.fixture
def mock_ai_studio_response() -> dict:
    """Мок ответа от AI Studio"""
    return {
        "result": {
            "alternatives": [
                {
                    "message": {
                        "role": "assistant",
                        "text": "Тестовый ответ от агента"
                    }
                }
            ]
        }
    }


@pytest.fixture
def expected_synthesis_output() -> dict:
    """Ожидаемый вывод от synthesis агента"""
    return {
        "urgency_level": "urgent",
        "specialist_referral": "педиатр-инфекционист",
        "reasoning": "Лихорадка с респираторными симптомами",
        "recommended_tests": ["ОАК", "СРБ", "Рентген грудной клетки"],
        "immediate_actions": ["Сбор анализов", "Консультация специалиста"],
        "red_flags": ["отказ от еды"],
        "follow_up_plan": "Повторный осмотр через 24 часа"
    }


# Моки для внешних сервисов
@pytest.fixture
def mock_yandex_cloud(monkeypatch):
    """Мок для Yandex Cloud API"""
    class MockYandexCloud:
        async def get_iam_token(self):
            return "test_iam_token"
        
        async def invoke_agent(self, agent_id: str, data: dict):
            return {
                "result": {
                    "alternatives": [
                        {
                            "message": {
                                "role": "assistant",
                                "text": f"Mock response from {agent_id}"
                            }
                        }
                    ]
                }
            }
    
    mock = MockYandexCloud()
    monkeypatch.setattr("app.core.ai_studio.YandexCloudClient", MockYandexCloud)
    return mock


@pytest.fixture
def mock_pdf_service(monkeypatch):
    """Мок для PDF сервиса"""
    class MockPDFService:
        async def generate_report(self, data: dict) -> str:
            return "/tmp/test_report.pdf"
        
        async def save_report(self, content: bytes, filename: str) -> str:
            return f"/exports/{filename}"
    
    mock = MockPDFService()
    monkeypatch.setattr("app.services.pdf_service.PDFService", MockPDFService)
    return mock


# Тестовые данные для различных сценариев
@pytest.fixture
def emergency_case_data() -> dict:
    """Данные для экстренного случая"""
    return {
        "raw_input": "Ребенок 2 месяца, температура 38.5°C, вялый, отказывается от питья, не мочился 8 часов"
    }


@pytest.fixture
def routine_case_data() -> dict:
    """Данные для планового случая"""
    return {
        "raw_input": "Ребенок 7 лет, температура 37.8°C 1 день, насморк, кашель, активный, пьет"
    }


@pytest.fixture
def complex_case_data() -> dict:
    """Данные для сложного случая"""
    return {
        "raw_input": "Ребенок 3 года, температура 39°C 10 дней, сыпь на теле, боли в суставах, потеря веса"
    }


# Вспомогательные функции для тестов
@pytest.fixture
def create_test_chat():
    """Функция для создания тестового чата"""
    async def _create_chat(db_session: AsyncSession, session_id: str = "test_session"):
        from app.db.models import ChatSession
        
        chat = ChatSession(
            session_id=session_id,
            status="active",
            metadata={"test": True}
        )
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)
        return chat
    
    return _create_chat


@pytest.fixture
def create_test_message():
    """Функция для создания тестового сообщения"""
    async def _create_message(db_session: AsyncSession, chat_id: int, content: str):
        from app.db.models import ChatMessage
        
        message = ChatMessage(
            chat_id=chat_id,
            role="user",
            content=content
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)
        return message
    
    return _create_message


# Настройки тестирования
def pytest_configure(config):
    """Настройка pytest"""
    config.addinivalue_line(
        "markers", "unit: Unit tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests"
    )
    config.addinivalue_line(
        "markers", "llm: Tests that call external LLM API"
    )


@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Переопределение настроек для тестов"""
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "log_level", "DEBUG")
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/1")