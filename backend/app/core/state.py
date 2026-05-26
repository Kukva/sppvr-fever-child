"""Определения состояний для LangGraph"""

import logging
from typing import TypedDict, Annotated, Sequence, Optional, Dict, Any, List
from langchain_core.messages import BaseMessage
from operator import add
from datetime import datetime
from enum import Enum


def merge_patient_data(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Редюсер для слияния данных пациента"""
    if not current:
        return update
    if not update:
        return current
    result = current.copy()
    result.update(update)
    return result


class UrgencyLevel(str, Enum):
    """Уровни срочности"""
    EMERGENCY = "emergency"
    URGENT = "urgent"
    ROUTINE = "routine"


class TemperaturePattern(str, Enum):
    """Паттерны температуры"""
    CONSTANT = "постоянная"
    INTERMITTENT = "интермиттирующая"
    WAVELIKE = "волнообразная"


class PatientData(TypedDict):
    """Структурированные данные о пациенте"""
    age_years: Optional[int]
    age_months: Optional[int]
    temperature_current: Optional[float]
    temperature_max: Optional[float]
    temperature_pattern: Optional[str]
    duration_days: Optional[int]
    symptoms: List[str]
    red_flags: List[str]
    anamnesis: Dict[str, Any]
    physical_exam: Dict[str, Any]
    lab_results: Dict[str, Any]
    missing_info: List[str]


class AgentOutput(TypedDict):
    """Результат работы агента"""
    agent_name: str
    timestamp: str
    output: Dict[str, Any]
    confidence: float
    questions_needed: List[str]
    execution_time_ms: Optional[int]


class SpecialistRecommendation(TypedDict):
    """Рекомендация по специалисту"""
    name: str
    reasons: List[str]
    priority: str  # "high", "medium", "low"
    timeframe: str  # "немедленно", "в течение 24 часов", "в течение 3-7 дней"
    purpose: str  # цель консультации


class GraphState(TypedDict):
    """Глобальное состояние графа"""
    
    # История диалога - используем простой список без редюсера
    messages: List[Dict[str, Any]]
    
    # Данные пациента - простой словарь без редюсера
    patient_data: Dict[str, Any]
    
    # Результаты агентов - простые поля без редюсеров
    intake_output: Optional[AgentOutput]
    data_completeness_checker_output: Optional[AgentOutput]
    triage_output: Optional[AgentOutput]
    hypothesis_generator_output: Optional[AgentOutput]
    infection_output: Optional[AgentOutput]
    immune_output: Optional[AgentOutput]
    oncology_output: Optional[AgentOutput]
    rare_disease_output: Optional[AgentOutput]
    question_output: Optional[AgentOutput]
    synthesis_output: Optional[AgentOutput]
    
    # Управление потоком
    urgency_level: Optional[UrgencyLevel]
    activated_specialists: List[str]
    questions_to_ask: List[Dict[str, Any]]
    needs_more_info: bool
    current_step: str
    
    # Поля для DATA_COMPLETENESS_CHECKER
    patient_data_complete: bool
    data_completeness_score: int
    missing_critical_data: List[str]
    red_flags_identified: List[str]
    
    # Поля для HYPOTHESIS_GENERATOR
    hypotheses: List[Dict[str, Any]]
    most_likely_diagnosis: Optional[str]
    key_discriminators: List[str]
    
    # Рекомендации
    primary_specialist: Optional[SpecialistRecommendation]
    additional_specialists: List[SpecialistRecommendation]
    required_tests: List[str]
    red_flags: List[str]
    recommendations_text: Optional[str]
    
    # Метаданные
    session_id: str
    created_at: str
    updated_at: str
    doctor_id: Optional[str]
    
    # Технические метаданные
    error_message: Optional[str]
    retry_count: int
    last_agent_executed: Optional[str]
    
    # Поля для управления диалогом
    current_question_index: int
    dialogue_phase: str  # "gathering_info", "diagnosis", "complete"
    awaiting_user_response: bool
    
    # Поля для адаптивного управления вопросами (по аналогии с MAI-DxO)
    diagnostic_confidence: float  # Уверенность в диагнозе (0.0-1.0)
    max_questions_allowed: int  # Максимальное количество вопросов
    questions_asked_count: int  # Количество уже заданных вопросов
    confidence_threshold: float  # Порог уверенности для прекращения вопросов
    case_complexity: str  # "low", "medium", "high" - сложность случая
    
    # Поля для обратной связи
    feedback_requested: bool  # Запрошена ли обратная связь
    feedback_received: bool  # Получена ли обратная связь

    # Режим выполнения (MAI-DxO-подобные режимы)
    run_mode: str  # "full" | "instant" | "question_only" | "budgeted"
    total_cost_units: int  # Учёт вызовов LLM (1 единица на вызов агента)
    max_cost_units: Optional[int]  # Для budgeted: лимит вызовов (None = без лимита)
    clinical_score: Optional[float]  # Опциональная клиническая оценка 1-5 после synthesis

    # Флаги оптимизации выполнения
    is_simple_case: Optional[bool]       # True для routine-случаев с высокой уверенностью (пропускаем специалистов)
    specialists_executed: Optional[bool] # True после параллельного прогона специалистов в route_to_specialists_node


class TriageOutput(TypedDict):
    """Результат работы TRIAGE AGENT"""
    urgency_level: UrgencyLevel
    fever_classification: str
    activate_agents: List[str]
    reasoning: str
    immediate_actions: List[str]


class InfectionOutput(TypedDict):
    """Результат работы INFECTION AGENT"""
    differential_diagnosis: List[Dict[str, Any]]
    most_likely: str
    cannot_exclude: List[str]
    questions_needed: List[str]


class ImmuneOutput(TypedDict):
    """Результат работы IMMUNE AGENT"""
    relevant_conditions: List[str]
    key_discriminators: List[str]
    specific_tests_needed: List[str]
    treatment_considerations: List[str]


class OncologyOutput(TypedDict):
    """Результат работы ONCOLOGY AGENT"""
    oncological_risk: str  # "high", "moderate", "low"
    red_flags_present: List[str]
    urgent_investigations: List[str]
    specialist_referral_needed: bool


class RareDiseaseOutput(TypedDict):
    """Результат работы RARE DISEASE AGENT"""
    rare_diagnoses_to_consider: List[str]
    pathognomonic_features_to_look_for: List[str]
    specialized_tests: List[str]
    need_genetic_counseling: bool


class QuestionOutput(TypedDict):
    """Результат работы QUESTION AGENT"""
    questions: List[Dict[str, Any]]
    priority: str  # "high", "medium", "low"
    reasoning: str


class SynthesisOutput(TypedDict):
    """Результат работы SYNTHESIS AGENT"""
    urgency_level: UrgencyLevel
    primary_specialist: SpecialistRecommendation
    additional_specialists: List[SpecialistRecommendation]
    required_tests: List[str]
    red_flags: List[str]
    recommendations_text: str
    reasoning: str
    confidence_level: str  # "high", "medium", "low"


class DataCompletenessCheckerOutput(TypedDict):
    """Результат работы DATA_COMPLETENESS_CHECKER AGENT"""
    patient_data_complete: bool
    data_completeness_score: int  # 0-100
    missing_critical_data: List[str]
    red_flags_identified: List[str]
    data_quality_assessment: str  # "excellent", "good", "fair", "poor"
    recommended_next_steps: List[str]


class HypothesisGeneratorOutput(TypedDict):
    """Результат работы HYPOTHESIS_GENERATOR AGENT"""
    hypotheses: List[Dict[str, Any]]  # [{"diagnosis": str, "probability": float, "reasoning": str}]
    most_likely_diagnosis: str
    key_discriminators: List[str]
    differential_diagnosis_ranked: List[str]
    confidence_level: str  # "high", "medium", "low"
    additional_investigations_needed: List[str]


# Вспомогательные функции для работы с состоянием
def create_initial_state(
    session_id: str,
    doctor_id: Optional[str] = None,
    run_mode: Optional[str] = None,
    max_cost_units: Optional[int] = None,
) -> GraphState:
    """Создание начального состояния графа"""
    now = datetime.now().isoformat()
    try:
        from app.config import settings
        _run_mode = run_mode or getattr(settings, "run_mode", "full")
        _max_cost = max_cost_units if max_cost_units is not None else getattr(settings, "max_cost_units", None)
    except Exception:
        _run_mode = run_mode or "full"
        _max_cost = max_cost_units
    
    return {
        "messages": [],
        "patient_data": {
            "age_years": None,
            "age_months": None,
            "temperature_current": None,
            "temperature_max": None,
            "temperature_pattern": None,
            "duration_days": None,
            "symptoms": [],
            "red_flags": [],
            "anamnesis": {},
            "physical_exam": {},
            "lab_results": {},
            "missing_info": []
        },
        "intake_output": None,
        "data_completeness_checker_output": None,
        "triage_output": None,
        "hypothesis_generator_output": None,
        "infection_output": None,
        "immune_output": None,
        "oncology_output": None,
        "rare_disease_output": None,
        "question_output": None,
        "synthesis_output": None,
        "urgency_level": None,
        "activated_specialists": [],
        "questions_to_ask": [],
        "needs_more_info": False,
        "current_step": "intake",
        "patient_data_complete": False,
        "data_completeness_score": 0,
        "missing_critical_data": [],
        "red_flags_identified": [],
        "hypotheses": [],
        "most_likely_diagnosis": None,
        "key_discriminators": [],
        "primary_specialist": None,
        "additional_specialists": [],
        "required_tests": [],
        "red_flags": [],
        "recommendations_text": None,
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "doctor_id": doctor_id,
        "error_message": None,
        "retry_count": 0,
        "last_agent_executed": None,
        "current_question_index": 0,
        "dialogue_phase": "gathering_info",
        "awaiting_user_response": False,
        # Поля для адаптивного управления вопросами
        "diagnostic_confidence": 0.0,  # Начальная уверенность
        "max_questions_allowed": 10,  # По умолчанию максимум 10 вопросов
        "questions_asked_count": 0,  # Пока не задано вопросов
        "confidence_threshold": 0.85,  # Порог уверенности 85% как в MAI-DxO
        "case_complexity": "medium",  # По умолчанию средняя сложность
        # Поля для обратной связи
        "feedback_requested": False,
        "feedback_received": False,
        # Режим и стоимость (MAI-DxO)
        "run_mode": _run_mode,
        "total_cost_units": 0,
        "max_cost_units": _max_cost,
        "clinical_score": None,
    }


def update_timestamp(state: GraphState) -> GraphState:
    """Обновление временной метки состояния"""
    new_state = state.copy()
    new_state["updated_at"] = datetime.now().isoformat()
    return new_state


def increment_cost_units(state: Dict[str, Any]) -> None:
    """Увеличивает счётчик вызовов LLM (in-place). Вызывать после успешного вызова агента."""
    state["total_cost_units"] = state.get("total_cost_units", 0) + 1


def add_agent_output(
    state: GraphState,
    agent_name: str,
    output: Dict[str, Any],
    confidence: float = 1.0,
    questions_needed: Optional[List[str]] = None,
    execution_time_ms: Optional[int] = None
) -> GraphState:
    """Добавление результата работы агента в состояние"""
    
    agent_output: AgentOutput = {
        "agent_name": agent_name,
        "timestamp": datetime.now().isoformat(),
        "output": output,
        "confidence": confidence,
        "questions_needed": questions_needed or [],
        "execution_time_ms": execution_time_ms
    }
    
    # Создаем новое состояние с обновленными данными
    new_state = state.copy()
    new_state[f"{agent_name}_output"] = agent_output
    new_state["last_agent_executed"] = agent_name
    new_state["updated_at"] = datetime.now().isoformat()
    
    return new_state


def update_patient_data(state: GraphState, patient_data_update: Dict[str, Any]) -> GraphState:
    """Обновление данных пациента с слиянием"""
    new_state = state.copy()
    
    # Сливаем данные пациента
    current_patient_data = new_state["patient_data"].copy()
    current_patient_data.update(patient_data_update)
    new_state["patient_data"] = current_patient_data
    new_state["updated_at"] = datetime.now().isoformat()
    
    return new_state


def add_message(state: GraphState, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> GraphState:
    """Добавление сообщения в историю диалога"""
    new_state = state.copy()
    
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {}
    }
    
    new_state["messages"] = new_state["messages"] + [message]
    new_state["updated_at"] = datetime.now().isoformat()
    
    return new_state


def extract_red_flags_from_patient_data(patient_data: PatientData) -> List[str]:
    """Извлечение красных флагов из данных пациента"""
    red_flags = []
    
    # Возрастные красные флаги
    age_years = patient_data.get("age_years", 0) or 0
    age_months = patient_data.get("age_months", 0) or 0
    temp_current = patient_data.get("temperature_current", 0) or 0
    
    # Проверяем общий возраст в месяцах
    total_months = age_years * 12 + age_months
    
    if total_months < 12 and temp_current > 38.0:
        red_flags.append("Возраст < 1 года с температурой > 38°C")
    
    if total_months < 3 and temp_current > 38.5:
        red_flags.append("Возраст < 3 месяцев с температурой > 38.5°C")
    
    # Температурные красные флаги
    temp_max = patient_data.get("temperature_max", 0) or 0
    if temp_max > 40.0:
        red_flags.append("Температура > 40°C")
    
    # Длительность лихорадки
    duration = patient_data.get("duration_days", 0) or 0
    if duration > 14:
        red_flags.append("Лихорадка > 14 дней")
    
    # Симптомы красных флагов
    symptoms = patient_data.get("symptoms", [])
    red_flag_symptoms = [
        "менингеальные симптомы",
        "нарушение сознания",
        "дыхательная недостаточность",
        "геморрагическая сыпь",
        "отказ от питья",
        "ночные поты",
        "потеря веса",
        "генерализованная лимфаденопатия",
        "гепатоспленомегалия",
        "боли в костях",
        "бледность",
        "петехии",
        "кровоточивость"
    ]
    
    for symptom in symptoms:
        if any(red_flag in symptom.lower() for red_flag in red_flag_symptoms):
            red_flags.append(symptom)
    
    # Добавляем уже существующие красные флаги
    red_flags.extend(patient_data.get("red_flags", []))
    
    return list(set(red_flags))  # Удаляем дубликаты


def determine_urgency_from_red_flags(red_flags: List[str]) -> UrgencyLevel:
    """Определение уровня срочности по красным флагам"""
    
    emergency_flags = [
        "менингеальные симптомы",
        "нарушение сознания",
        "дыхательная недостаточность",
        "геморрагическая сыпь",
        "отказ от питья",
        "невозможность разбудить"
    ]
    
    urgent_flags = [
        "Температура > 40°C",
        "Возраст < 3 месяцев",
        "Лихорадка > 14 дней",
        "ночные поты",
        "потеря веса",
        "генерализованная лимфаденопатия",
        "гепатоспленомегалия"
    ]
    
    # Проверка на экстренные флаги
    if any(flag in " ".join(red_flags).lower() for flag in emergency_flags):
        return UrgencyLevel.EMERGENCY
    
    # Проверка на срочные флаги
    if any(flag in " ".join(red_flags) for flag in urgent_flags):
        return UrgencyLevel.URGENT
    
    return UrgencyLevel.ROUTINE


def calculate_case_complexity(patient_data: Dict[str, Any], red_flags: List[str]) -> str:
    """Определение сложности случая на основе данных пациента и красных флагов"""
    
    # Критерии высокой сложности
    high_complexity_flags = [
        "менингеальные симптомы",
        "нарушение сознания",
        "дыхательная недостаточность",
        "геморрагическая сыпь",
        "генерализованная лимфаденопатия",
        "гепатоспленомегалия",
        "боли в костях",
        "ночные поты",
        "потеря веса"
    ]
    
    # Критерии средней сложности
    medium_complexity_flags = [
        "Температура > 40°C",
        "Возраст < 3 месяцев",
        "Лихорадка > 14 дней",
        "отказ от питья"
    ]
    
    # Проверяем наличие красных флагов высокой сложности
    high_complexity_count = sum(1 for flag in red_flags if any(hc_flag in flag.lower() for hc_flag in high_complexity_flags))
    
    # Проверяем наличие красных флагов средней сложности
    medium_complexity_count = sum(1 for flag in red_flags if any(mc_flag in flag for mc_flag in medium_complexity_flags))
    
    # Дополнительные факторы сложности
    age_years = patient_data.get("age_years", 0) or 0
    age_months = patient_data.get("age_months", 0) or 0
    total_months = age_years * 12 + age_months
    
    # Очень маленький возраст или длительная лихорадка увеличивают сложность
    if total_months < 3:
        high_complexity_count += 1
    
    duration_days = patient_data.get("duration_days", 0) or 0
    if duration_days > 14:
        high_complexity_count += 1
    elif duration_days > 7:
        medium_complexity_count += 1
    
    # Определение сложности
    if high_complexity_count >= 2 or (high_complexity_count >= 1 and medium_complexity_count >= 2):
        return "high"
    elif high_complexity_count >= 1 or medium_complexity_count >= 2:
        return "medium"
    else:
        return "low"


def update_diagnostic_confidence(
    state: GraphState,
    new_confidence: float,
    reasoning: Optional[str] = None
) -> GraphState:
    """Обновление диагностической уверенности"""
    new_state = state.copy()
    new_state["diagnostic_confidence"] = max(0.0, min(1.0, new_confidence))  # Ограничиваем диапазон 0.0-1.0
    new_state["updated_at"] = datetime.now().isoformat()
    
    # Логируем изменение уверенности
    logger = logging.getLogger(__name__)
    logger.info(f"Updated diagnostic confidence to {new_confidence:.2f}")
    if reasoning:
        logger.info(f"Reasoning: {reasoning}")
    
    return new_state


def should_continue_questions(state: GraphState) -> bool:
    """Определяет, следует ли продолжать задавать вопросы с динамическим подходом"""
    
    # Если в фазе диагностики - не задаем вопросы
    if state.get("dialogue_phase") == "diagnosis":
        return False
    
    # Если достигнут порог уверенности - прекращаем (основной критерий)
    confidence = state.get("diagnostic_confidence", 0.0)
    confidence_threshold = state.get("confidence_threshold", 0.85)
    
    if confidence >= confidence_threshold:
        return False
    
    # Динамическая оценка необходимости дополнительных вопросов
    questions_asked = state.get("questions_asked_count", 0)
    case_complexity = state.get("case_complexity", "medium")
    
    # Адаптивные пороги в зависимости от сложности
    if case_complexity == "low":
        # Для простых случаев - меньше вопросов
        soft_limit = 5
        hard_limit = 8
    elif case_complexity == "high":
        # Для сложных случаев - больше вопросов
        soft_limit = 10
        hard_limit = 20
    else:  # medium
        soft_limit = 7
        hard_limit = 15
    
    # Если достигнут жесткий лимит - прекращаем в любом случае
    if questions_asked >= hard_limit:
        return False
    
    # Если достигнут мягкий лимит, но уверенность все еще низкая - продолжаем с осторожностью
    if questions_asked >= soft_limit:
        # Продолжаем только если уверенность очень низкая (<50%)
        return confidence < 0.5
    
    # В остальных случаях - продолжаем
    return True


def calculate_question_priority(state: GraphState) -> str:
    """Рассчитывает приоритет генерации вопросов на основе текущего состояния"""
    
    confidence = state.get("diagnostic_confidence", 0.0)
    questions_asked = state.get("questions_asked_count", 0)
    case_complexity = state.get("case_complexity", "medium")
    
    # Высокий приоритет: низкая уверенность и мало вопросов задано
    if confidence < 0.4 and questions_asked < 5:
        return "high"
    
    # Средний приоритет: средняя уверенность или умеренное количество вопросов
    if (confidence < 0.7 and questions_asked < 10) or case_complexity == "high":
        return "medium"
    
    # Низкий приоритет: высокая уверенность или много вопросов задано
    return "low"


def estimate_confidence_gain(state: GraphState) -> float:
    """Оценивает потенциальный прирост уверенности от дополнительного вопроса"""
    
    confidence = state.get("diagnostic_confidence", 0.0)
    questions_asked = state.get("questions_asked_count", 0)
    case_complexity = state.get("case_complexity", "medium")
    
    # Базовый прирост уменьшается с каждым вопросом
    base_gain = 0.1 * (0.9 ** questions_asked)
    
    # Корректировка в зависимости от сложности
    if case_complexity == "high":
        base_gain *= 1.2  # Сложные случаи могут дать больше информации
    elif case_complexity == "low":
        base_gain *= 0.8  # Простые случаи дают меньше новой информации
    
    # Уменьшаем прирост при высокой уверенности
    if confidence > 0.8:
        base_gain *= 0.5
    
    return max(0.01, base_gain)  # Минимальный прирост 1%


def calculate_max_questions(complexity: str) -> int:
    """Определяет максимальное количество вопросов на основе сложности случая"""
    if complexity == "high":
        return 15  # Больше вопросов для сложных случаев
    elif complexity == "medium":
        return 10  # Стандартное количество
    else:  # low
        return 7   # Меньше вопросов для простых случаев