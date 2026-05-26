"""Основное приложение LangGraph с мультиагентным графом"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Literal, Callable, Awaitable
from collections.abc import Mapping
from datetime import datetime

from langgraph.graph import StateGraph, END, START
# from langgraph.checkpoint.postgres import PostgresSaver  # Временно отключено
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.core.state import (
    GraphState, create_initial_state, update_timestamp, add_agent_output,
    update_patient_data, add_message, increment_cost_units,
    UrgencyLevel, extract_red_flags_from_patient_data, determine_urgency_from_red_flags,
    calculate_case_complexity, update_diagnostic_confidence, should_continue_questions,
    calculate_max_questions, calculate_question_priority, estimate_confidence_gain
)
from app.core.ai_studio import get_ai_studio_client, YandexAIStudioError
from app.core.redis_client import get_redis_manager
from app.core.feedback_parser import parse_feedback_response
from app.core.retry import RetryPolicies, RetryPolicy
from app.core.metrics import timing_decorator, get_performance_metrics
from app.config import settings

logger = logging.getLogger(__name__)

# Ключи состояния, из выходов которых собираем клинические источники (поле output.sources)
_CLINICAL_SOURCE_STATE_KEYS: tuple = (
    "intake_output",
    "data_completeness_checker_output",
    "triage_output",
    "hypothesis_generator_output",
    "infection_output",
    "immune_output",
    "oncology_output",
    "rare_disease_output",
    "question_output",
    "synthesis_output",
)


def _is_minzdrav_cr_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.lower().strip()
    return "cr.minzdrav.gov.ru" in u


def _normalize_source_dict(raw: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Приводит элемент sources к плоскому dict для API/UI."""
    if not isinstance(raw, dict):
        return None
    title = (raw.get("title") or "").strip()
    url = (raw.get("url") or "").strip()
    if not title and not url:
        return None
    out: Dict[str, str] = {
        "title": title or "Источник",
        "url": url,
        "description": (raw.get("description") or "").strip(),
    }
    if raw.get("section_or_paragraph"):
        out["section_or_paragraph"] = str(raw["section_or_paragraph"]).strip()
    if raw.get("verbatim_excerpt"):
        out["verbatim_excerpt"] = str(raw["verbatim_excerpt"]).strip()
    if raw.get("supports_claim"):
        out["supports_claim"] = str(raw["supports_claim"]).strip()
    return out


def _source_dedup_key(item: Dict[str, str]) -> tuple:
    return (
        item.get("url", ""),
        item.get("section_or_paragraph", ""),
        item.get("verbatim_excerpt", "")[:240],
        item.get("supports_claim", ""),
    )


def _coerce_unit_interval(value: Any, default: float = 0.0) -> float:
    """Число 0–1 для уверенности/вклада: LLM часто отдаёт str, «30%» или число > 1."""
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        x = float(value)
        if x > 1.0:
            return max(0.0, min(1.0, x / 100.0))
        return max(0.0, min(1.0, x))
    if isinstance(value, str):
        s = value.strip().replace(",", ".").replace(" ", "")
        if not s:
            return default
        if s.endswith("%"):
            try:
                return max(0.0, min(1.0, float(s[:-1]) / 100.0))
            except ValueError:
                return default
        try:
            x = float(s)
            if x > 1.0:
                return max(0.0, min(1.0, x / 100.0))
            return max(0.0, min(1.0, x))
        except ValueError:
            return default
    return default


def _recent_dialogue_for_question(state: Mapping) -> List[Dict[str, str]]:
    """Последние реплики user/assistant для адаптивного следующего вопроса."""
    msgs = state.get("messages") or []
    out: List[Dict[str, str]] = []
    for m in msgs[-14:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        raw = m.get("content", "")
        text = raw if isinstance(raw, str) else str(raw or "")
        text = text.strip()
        if not text:
            continue
        if len(text) > 1500:
            text = text[:1500] + "…"
        out.append({"role": role, "content": text})
    return out


# Маппинг узла графа → (название для UI, краткое описание) — для progress и workflow
AGENT_PROGRESS_LABELS: Dict[str, tuple] = {
    "intake": ("Приём данных", "Сбор жалоб, возраста, температуры и симптомов пациента."),
    "data_completeness_checker": ("Проверка полноты данных", "Оценка достаточности данных для первичного заключения."),
    "triage": ("Триаж", "Определение срочности и активация направлений диагностики."),
    "hypothesis_generator": ("Гипотезы", "Формирование дифференциальных диагнозов."),
    "question": ("Уточняющие вопросы", "Генерация вопросов для повышения уверенности."),
    "infection": ("Инфекционист", "Оценка инфекционных причин лихорадки."),
    "immune": ("Иммунолог", "Оценка иммунологических причин."),
    "oncology": ("Онколог", "Оценка онкологических рисков."),
    "rare_disease": ("Редкие заболевания", "Учёт редких причин лихорадки."),
    "synthesis": ("Синтез", "Финальное заключение и маршрутизация к специалисту."),
    "feedback_request": ("Запрос обратной связи", "Уточнение потребностей пользователя."),
    "route_to_specialists": ("Маршрутизация к специалистам", "Распределение по профильным агентам."),
}


class FeverRoutingGraph:
    """Мультиагентный граф для маршрутизации детей с лихорадкой"""
    
    def __init__(self):
        self.graph = None
        self.checkpointer = None
        self._initialized = False
        self.redis_manager = None
    
    async def initialize(self):
        """Инициализация графа и Redis"""
        if self._initialized:
            return
        
        try:
            # Инициализация Redis менеджера
            self.redis_manager = await get_redis_manager()
            logger.info("Redis manager initialized")
            
            # Временно отключаем checkpointer для отладки
            self.checkpointer = None
            
            # Построение графа
            self.graph = self._build_graph()
            
            self._initialized = True
            logger.info("LangGraph initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize LangGraph: {str(e)}")
            raise
    
    def _build_graph(self) -> StateGraph:
        """Построение графа агентов для пошагового диалога"""
        
        logger.info("=== BUILDING GRAPH ===")
        
        # Создание графа
        workflow = StateGraph(GraphState)
        
        # Добавление узлов
        workflow.add_node("intake", self._intake_node)
        workflow.add_node("data_completeness_checker", self._data_completeness_checker_node)
        workflow.add_node("triage", self._triage_node)
        workflow.add_node("hypothesis_generator", self._hypothesis_generator_node)
        workflow.add_node("question", self._question_node)
        workflow.add_node("route_to_specialists", self._route_to_specialists_node)
        workflow.add_node("infection", self._infection_node)
        workflow.add_node("immune", self._immune_node)
        workflow.add_node("oncology", self._oncology_node)
        workflow.add_node("rare_disease", self._rare_disease_node)
        workflow.add_node("synthesis", self._synthesis_node)
        workflow.add_node("feedback_request", self._feedback_request_node)
        
        logger.info("Added all nodes to graph")
        
        # Определение переходов
        workflow.set_entry_point("intake")
        workflow.add_edge("intake", "data_completeness_checker")
        logger.info("Added edge: intake -> data_completeness_checker")
        
        # Условные переходы после data_completeness_checker
        workflow.add_conditional_edges(
            "data_completeness_checker",
            self._after_data_check,
            {
                "triage": "triage",
                "question": "question"
            }
        )
        logger.info("Added conditional edges from data_completeness_checker")
        
        # Условные переходы после triage (synthesis — для режима instant)
        workflow.add_conditional_edges(
            "triage",
            self._should_continue_to_specialists,
            {
                "hypothesis_generator": "hypothesis_generator",
                "specialists": "route_to_specialists",
                "question": "question",
                "synthesis": "synthesis",
                "end": END
            }
        )
        logger.info("Added conditional edges from triage")
        
        # Условные переходы после hypothesis_generator
        workflow.add_conditional_edges(
            "hypothesis_generator",
            self._should_continue_dialogue,
            {
                "specialists": "route_to_specialists",
                "question": "question",
                "end": END
            }
        )
        logger.info("Added conditional edges from hypothesis_generator")
        
        
        # Маршрутизация к специалистам
        workflow.add_conditional_edges(
            "route_to_specialists",
            self._route_to_specialists,
            {
                "infection": "infection",
                "immune": "immune",
                "oncology": "oncology",
                "rare_disease": "rare_disease",
                "synthesis": "synthesis"
            }
        )
        logger.info("Added conditional edges from route_to_specialists")
        
        # Все специалисты ведут к синтезу
        workflow.add_edge("infection", "synthesis")
        workflow.add_edge("immune", "synthesis")
        workflow.add_edge("oncology", "synthesis")
        workflow.add_edge("rare_disease", "synthesis")
        logger.info("Added edges from specialists to synthesis")
        
        # После вопросов - проверяем полноту данных снова или завершаем
        workflow.add_conditional_edges(
            "question",
            self._after_questions,
            {
                "data_check": "data_completeness_checker",
                "end": END
            }
        )
        logger.info("Added conditional edges from question")
        
        # После синтеза запрашиваем обратную связь
        workflow.add_edge("synthesis", "feedback_request")
        logger.info("Added edge: synthesis -> feedback_request")
        
        # После запроса обратной связи завершаем
        workflow.add_edge("feedback_request", END)
        logger.info("Added edge: feedback_request -> END")
        
        # Компиляция графа (временно без checkpointer)
        compiled_graph = workflow.compile()
        logger.info("Graph compiled successfully")
        return compiled_graph
    
    @timing_decorator("intake")
    async def _intake_node(self, state: GraphState) -> GraphState:
        """Узел INTAKE AGENT - структурирование данных в диалоговом режиме с оценкой уверенности"""
        try:
            # Безопасное получение session_id из состояния
            session_id = state.get('session_id', 'unknown')
            logger.info(f"Executing INTAKE agent for session {session_id}")
            logger.debug(f"State type: {type(state)}")
        except Exception as e:
            logger.error(f"Error in _intake_node accessing session_id: {str(e)}")
            session_id = 'unknown'
        
        try:
            # Получение последнего сообщения
            if not state["messages"]:
                raise ValueError("No messages in state")
            
            last_message = state["messages"][-1]
            if isinstance(last_message, dict):
                user_input = last_message.get("content", "")
            else:
                user_input = str(last_message)
            
            # Проверяем, это первое сообщение или ответ на вопрос
            is_first_message = len(state["messages"]) == 1
            dialogue_phase = state.get("dialogue_phase", "gathering_info")
            is_answer_to_question = dialogue_phase == "gathering_info" and not is_first_message
            
            # Проверяем, это ответ на запрос обратной связи
            feedback_requested = state.get("feedback_requested", False)
            is_feedback_response = feedback_requested and not state.get("feedback_received", False)
            
            # Если это ответ на запрос обратной связи, обрабатываем его отдельно
            if is_feedback_response:
                # Парсим ответ пользователя на обратную связь
                parsed_feedback = parse_feedback_response(user_input)
                was_helpful = parsed_feedback["was_helpful"]
                helped_decision = parsed_feedback["helped_decision"]
                rating = parsed_feedback["rating"]
                comment = parsed_feedback["comment"]
                
                new_state = state.copy()
                new_state["feedback_received"] = True
                new_state["awaiting_user_response"] = False
                
                # Сохраняем обратную связь в БД асинхронно
                try:
                    from app.db.session import get_db_session
                    from app.db.repositories import FeedbackRepository
                    import asyncio
                    
                    async def save_feedback():
                        try:
                            async with get_db_session() as db:
                                feedback_repo = FeedbackRepository(db)
                                # Проверяем, не была ли уже оставлена обратная связь
                                existing = await feedback_repo.get_session_feedback(session_id)
                                if not existing:
                                    await feedback_repo.create_feedback(
                                        session_id=session_id,
                                        was_helpful=was_helpful,
                                        helped_decision=helped_decision,
                                        rating=rating,
                                        comment=comment
                                    )
                                    logger.info(f"Feedback saved for session {session_id}: helpful={was_helpful}, decision={helped_decision}, rating={rating}")
                        except Exception as e:
                            logger.error(f"Error saving feedback: {str(e)}")
                    
                    # Запускаем сохранение в фоне
                    asyncio.create_task(save_feedback())
                except Exception as e:
                    logger.warning(f"Could not save feedback immediately: {str(e)}")
                
                # Формируем ответ
                response_text = "Спасибо за обратную связь! "
                if was_helpful:
                    response_text += "Рады, что рекомендации были полезны. "
                if helped_decision:
                    response_text += "Очень важно, что мы помогли вам принять решение. "
                response_text += "Ваше мнение поможет нам улучшить систему."
                
                new_state = add_message(new_state, "assistant", response_text)
                
                logger.info(f"Feedback response processed for session {session_id}: helpful={was_helpful}, decision={helped_decision}, rating={rating}")
                return new_state
            
            # Вызов агента с retry механизмом
            client = await get_ai_studio_client()
            
            async def call_intake_agent():
                return await client.call_agent(
                agent_name="intake",
                prompt=user_input,
                context={
                    "previous_data": state["patient_data"],
                    "is_first_message": is_first_message,
                    "is_answer_to_question": is_answer_to_question,
                    "dialogue_mode": True
                }
            )
            
            # Используем retry для критического агента
            try:
                result = await RetryPolicies.CRITICAL_AGENT.execute(call_intake_agent)
            except Exception as e:
                logger.error(f"INTAKE agent failed after retries: {str(e)}")
                # Fallback: используем базовые данные из сообщения пользователя
                result = {
                    "success": False,
                    "error": str(e),
                    "parsed_data": self._get_fallback_intake_data(user_input, state["patient_data"])
                }
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                
                # Валидация результата агента
                if not self._validate_agent_output("intake", parsed_data):
                    logger.warning(f"Invalid intake output for session {session_id}, attempting to use partial data")
                    # Пытаемся использовать частичные данные
                
                # Обновление данных пациента
                updated_patient_data = self._update_patient_data_from_intake(
                    state["patient_data"], parsed_data
                )
                
                # Извлечение красных флагов
                red_flags = extract_red_flags_from_patient_data(updated_patient_data)
                updated_patient_data["red_flags"] = red_flags
                
                # Создаем новое состояние с помощью вспомогательных функций
                new_state = update_patient_data(state, updated_patient_data)
                new_state["current_step"] = "intake_completed"
                
                # Адаптивные вопросы: после ответа на вопрос сбрасываем пул — следующий вопрос
                # сгенерируется заново с учётом новых вводных (не идём по заранее сгенерированному списку).
                if is_answer_to_question and dialogue_phase == "gathering_info":
                    new_state["questions_to_ask"] = []
                    new_state["current_question_index"] = 0
                
                # Расчет начальной диагностической уверенности на основе полноты данных
                data_completeness = self._calculate_initial_confidence(updated_patient_data, red_flags)
                new_state = update_diagnostic_confidence(
                    new_state,
                    data_completeness,
                    "Initial confidence based on data completeness"
                )
                
                # Определение сложности случая
                case_complexity = calculate_case_complexity(updated_patient_data, red_flags)
                new_state["case_complexity"] = case_complexity
                new_state["max_questions_allowed"] = calculate_max_questions(case_complexity)
                
                # Добавление результата агента
                new_state = add_agent_output(
                    new_state,
                    "intake",
                    parsed_data,
                    confidence=1.0,
                    execution_time_ms=result.get("execution_time_ms")
                )
                increment_cost_units(new_state)
                
                # Формирование ответа в диалоговом режиме
                if is_answer_to_question:
                    # Краткое подтверждение получения ответа
                    response_text = "Понял(а). "
                else:
                    # Стандартная логика для первого сообщения
                    if is_first_message:
                        # Первичное приветствие и подтверждение полученных данных
                        response_text = "Здравствуйте! Я помогу вам определить, к какому специалисту направить ребенка.\n\n"
                        response_text += "Я получил(а) следующую информацию:\n"
                        
                        if updated_patient_data.get("age_years") or updated_patient_data.get("age_months"):
                            age_text = ""
                            if updated_patient_data.get("age_years"):
                                age_text += f"{updated_patient_data['age_years']} год"
                            if updated_patient_data.get("age_months"):
                                age_text += f" {updated_patient_data['age_months']} месяцев"
                            response_text += f"• Возраст: {age_text}\n"
                        
                        if updated_patient_data.get("temperature_current"):
                            response_text += f"• Температура: {updated_patient_data['temperature_current']}°C\n"
                        
                        if updated_patient_data.get("duration_days"):
                            response_text += f"• Длительность лихорадки: {updated_patient_data['duration_days']} дней\n"
                        
                        if updated_patient_data.get("symptoms"):
                            response_text += f"• Симптомы: {', '.join(updated_patient_data['symptoms'])}\n"
                        
                        # Добавляем информацию о сложности и уверенности
                        response_text += f"\n📊 Оценка сложности случая: {case_complexity}"
                        response_text += f"\n📈 Начальная диагностическая уверенность: {data_completeness:.1%}"
                        
                        if red_flags:
                            response_text += f"\n⚠️ Выявлены красные флаги: {len(red_flags)}"
                        
                        response_text += (
                            "\n\nДалее я буду задавать **по одному** уточняющему вопросу и подстраивать "
                            "следующий под ваши ответы."
                        )
                    else:
                        # Уточняющий ответ
                        response_text = "Спасибо за дополнительную информацию. Я учел(а) ее в анализе."
                
                new_state = add_message(new_state, "assistant", response_text)
                
                logger.info(f"INTAKE completed: complexity={case_complexity}, confidence={data_completeness:.2f}, red_flags={len(red_flags)}")
                
                return new_state
                
            else:
                # Обработка ошибки с fallback данными
                error_msg = f"INTAKE agent failed: {result.get('error', 'Unknown error')}"
                logger.warning(f"Using fallback data for session {session_id}: {error_msg}")
                
                # Используем fallback данные если они есть
                fallback_data = result.get("parsed_data")
                if fallback_data:
                    updated_patient_data = self._update_patient_data_from_intake(
                        state["patient_data"], fallback_data
                    )
                    red_flags = extract_red_flags_from_patient_data(updated_patient_data)
                    updated_patient_data["red_flags"] = red_flags
                    
                    new_state = update_patient_data(state, updated_patient_data)
                    new_state["current_step"] = "intake_completed"
                    new_state["error_message"] = error_msg  # Сохраняем ошибку для логирования
                    
                    # Используем минимальную уверенность для fallback
                    new_state = update_diagnostic_confidence(new_state, 0.5, "Fallback mode")
                    
                    new_state = add_message(
                        new_state, 
                        "assistant", 
                        "Я обработал ваше сообщение с ограниченными возможностями. Пожалуйста, уточните информацию."
                    )
                    return new_state
                else:
                    # Если fallback данных нет, возвращаем ошибку
                    new_state = state.copy()
                    new_state["error_message"] = error_msg
                    new_state = add_message(new_state, "assistant", "Произошла ошибка при обработке данных. Попробуйте переформулировать.")
                    return new_state
            
        except Exception as e:
            logger.error(f"INTAKE node error: {str(e)}")
            new_state = state.copy()
            new_state["error_message"] = str(e)
            new_state = add_message(new_state, "assistant", "Произошла ошибка. Попробуйте еще раз.")
            return new_state
    
    def _calculate_initial_confidence(self, patient_data: Dict[str, Any], red_flags: List[str]) -> float:
        """Расчет начальной диагностической уверенности на основе полноты данных"""
        
        confidence = 0.0
        
        # Базовая уверенность за наличие основных данных
        if patient_data.get("age_years") or patient_data.get("age_months"):
            confidence += 0.15
        
        if patient_data.get("temperature_current"):
            confidence += 0.15
        
        if patient_data.get("duration_days"):
            confidence += 0.15
        
        # Дополнительная уверенность за детализацию
        if patient_data.get("temperature_max"):
            confidence += 0.05
        
        if patient_data.get("temperature_pattern"):
            confidence += 0.05
        
        # Уверенность за симптомы
        symptoms = patient_data.get("symptoms", [])
        if symptoms:
            confidence += min(0.2, len(symptoms) * 0.05)  # Максимум 0.2 за симптомы
        
        # Уверенность за анамнез
        anamnesis = patient_data.get("anamnesis", {})
        if anamnesis:
            confidence += 0.1
        
        # Корректировка на основе красных флагов
        if red_flags:
            # Красные флаги могут как увеличить, так и уменьшить уверенность
            critical_flags = [
                "менингеальные симптомы",
                "нарушение сознания",
                "дыхательная недостаточность",
                "геморрагическая сыпь"
            ]
            
            has_critical = any(flag in " ".join(red_flags).lower() for flag in critical_flags)
            if has_critical:
                confidence += 0.1  # Критические флаги увеличивают уверенность в необходимости экстренных действий
            else:
                confidence -= 0.05  # Некритические флаги снижают уверенность из-за неопределенности
        
        # Ограничиваем диапазон
        return max(0.1, min(0.6, confidence))  # Начальная уверенность не может быть слишком высокой
    
    @timing_decorator("data_completeness_checker")
    async def _data_completeness_checker_node(self, state: GraphState) -> GraphState:
        """Узел DATA_COMPLETENESS_CHECKER AGENT - проверка полноты данных"""
        logger.info("=== DATA_COMPLETENESS_CHECKER NODE STARTED ===")
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Executing DATA_COMPLETENESS_CHECKER agent for session {session_id}")
        
        try:
            # Подготовка контекста (patient_data — уже слитые поля после intake, в т.ч. lab_results)
            _pat = state.get("patient_data") or {}
            context = {
                "intake_output": state.get("intake_output", {}),
                "patient_data_excerpt": {
                    "lab_results": _pat.get("lab_results"),
                    "anamnesis": _pat.get("anamnesis"),
                    "physical_exam": _pat.get("physical_exam"),
                    "symptoms": _pat.get("symptoms"),
                    "duration_days": _pat.get("duration_days"),
                },
            }
            
            # Вызов агента
            client = await get_ai_studio_client()
            result = await client.call_agent(
                agent_name="data_completeness_checker",
                prompt="Проведи оценку полноты данных",
                context=context
            )
            
            # Создаем новое состояние
            new_state = state.copy()
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                
                # Валидация результата агента
                if not self._validate_data_completeness_output(parsed_data):
                    logger.warning(f"Invalid data_completeness_checker output for session {session_id}, using defaults")
                    parsed_data = {
                        "patient_data_complete": False,
                        "data_completeness_score": 0,
                        "missing_critical_data": parsed_data.get("missing_critical_data", []),
                        "red_flags_identified": parsed_data.get("red_flags_identified", [])
                    }
                
                # Обновление полноты данных
                new_state["patient_data_complete"] = parsed_data.get("patient_data_complete", False)
                new_state["data_completeness_score"] = parsed_data.get("data_completeness_score", 0)
                new_state["missing_critical_data"] = parsed_data.get("missing_critical_data", [])
                new_state["red_flags_identified"] = parsed_data.get("red_flags_identified", [])
                
                # Обновление состояния
                new_state["current_step"] = "data_check_completed"
                
                # Добавление результата агента
                new_state = add_agent_output(
                    new_state,
                    "data_completeness_checker",
                    parsed_data,
                    confidence=1.0,
                    execution_time_ms=result.get("execution_time_ms")
                )
                increment_cost_units(new_state)
                
                # Добавление ответа агента
                completeness_score = new_state["data_completeness_score"]
                missing_data = new_state["missing_critical_data"]
                red_flags = new_state["red_flags_identified"]
                
                response_text = f"Проверка полноты данных завершена. Оценка: {completeness_score}/100\n"
                
                if missing_data:
                    response_text += f"Отсутствуют важные данные: {', '.join(missing_data)}\n"
                
                if red_flags:
                    response_text += f"Выявлены красные флаги: {', '.join(red_flags)}\n"
                
                # НОВАЯ ЛОГИКА СООБЩЕНИЙ
                # Добавляем сообщение только если не в фазе сбора информации И не в фазе диагностики
                if state.get("dialogue_phase") not in ["gathering_info", "diagnosis"]:
                    if completeness_score >= 80:
                        response_text += "✅ Данных достаточно для качественной диагностики."
                    elif completeness_score >= 70:
                        # Проверяем на критические emergency флаги
                        critical_emergency_flags = [
                            "нарушение сознания",
                            "судороги",
                            "дыхательная недостаточность",
                            "геморрагическая сыпь",
                            "невозможность разбудить"
                        ]
                        has_critical_emergency = any(
                            flag.lower() in " ".join(red_flags).lower()
                            for flag in critical_emergency_flags
                        )
                        
                        if has_critical_emergency:
                            response_text += "⚠️ КРИТИЧЕСКАЯ СИТУАЦИЯ - начинаем экстренную оценку."
                        else:
                            response_text += "⚠️ Данных недостаточно. Мне нужно задать уточняющие вопросы."
                    else:
                        response_text += "❌ Данных недостаточно для диагностики. Необходимо собрать дополнительную информацию."
                    
                    new_state = add_message(new_state, "assistant", response_text)
                
                logger.info(f"DATA_COMPLETENESS_CHECKER completed: score={completeness_score}, missing={len(missing_data)}, red_flags={len(red_flags)}")
                
            else:
                error_msg = f"DATA_COMPLETENESS_CHECKER agent failed: {result.get('error', 'Unknown error')}"
                new_state["error_message"] = error_msg
                # Установка значений по умолчанию
                new_state["patient_data_complete"] = False
                new_state["data_completeness_score"] = 0
                new_state["missing_critical_data"] = []
                new_state["red_flags_identified"] = []
                logger.warning(error_msg)
            
            return new_state
            
        except Exception as e:
            logger.error(f"DATA_COMPLETENESS_CHECKER node error: {str(e)}")
            new_state = state.copy()
            new_state["error_message"] = str(e)
            new_state["patient_data_complete"] = False
            new_state["data_completeness_score"] = 0
            new_state["missing_critical_data"] = []
            new_state["red_flags_identified"] = []
            return new_state
    
    @timing_decorator("triage")
    async def _triage_node(self, state: GraphState) -> GraphState:
        """Узел TRIAGE AGENT - сортировка и оценка срочности"""
        logger.info("=== TRIAGE NODE STARTED ===")
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Executing TRIAGE agent for session {session_id}")
        logger.info(f"State keys in triage: {list(state.keys())}")
        
        try:
            # Подготовка контекста
            context = {
                "structured_patient_data": state["patient_data"]
            }
            
            # Вызов агента с retry механизмом
            client = await get_ai_studio_client()
            
            async def call_triage_agent():
                return await client.call_agent(
                agent_name="triage",
                prompt="Проведи сортировку пациента",
                context=context
            )
            
            # Используем retry для критического агента
            try:
                result = await RetryPolicies.CRITICAL_AGENT.execute(call_triage_agent)
            except Exception as e:
                logger.error(f"TRIAGE agent failed after retries: {str(e)}")
                # Fallback: используем значения по умолчанию
                result = {
                    "success": False,
                    "error": str(e),
                    "parsed_data": self._get_fallback_triage_data(state)
                }
            
            # Создаем новое состояние
            new_state = state.copy()
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                
                # Обновление уровня срочности с обработкой невалидных значений
                urgency_str = parsed_data.get("urgency_level", "routine")
                try:
                    urgency = UrgencyLevel(urgency_str)
                except ValueError:
                    # Если агент вернул невалидное значение, используем ROUTINE по умолчанию
                    logger.warning(f"Invalid urgency level '{urgency_str}' from triage agent, using ROUTINE")
                    urgency = UrgencyLevel.ROUTINE
                new_state["urgency_level"] = urgency

                # Сохраняем детальную зону (5-зонная маршрутизация v2)
                triage_zone = parsed_data.get("triage_zone")
                if triage_zone:
                    new_state["triage_zone"] = triage_zone

                # Обновление активированных специалистов
                activated_agents = parsed_data.get("activate_agents", [])
                # Приводим к верхнему регистру для consistency
                activated_agents = [agent.upper() for agent in activated_agents]
                new_state["activated_specialists"] = activated_agents
                
                # Обновление состояния
                new_state["current_step"] = "triage_completed"
                
                # Добавление результата агента
                new_state = add_agent_output(
                    new_state,
                    "triage",
                    parsed_data,
                    confidence=1.0,
                    execution_time_ms=result.get("execution_time_ms")
                )
                increment_cost_units(new_state)
                
                # Добавляем ответ агента только если не в фазе сбора информации и не в фазе диагностики
                if state.get("dialogue_phase") not in ["gathering_info", "diagnosis"]:
                    response_text = f"Оценка срочности: {urgency.value.upper()}\n"
                    response_text += f"Активированные специалисты: {', '.join(activated_agents)}"
                    new_state = add_message(new_state, "assistant", response_text)
                
                # Отладочные логи
                logger.info(f"TRIAGE completed: urgency={urgency_str}, activated_specialists={activated_agents}")
                logger.info(f"State before conditional edge: activated_specialists={new_state.get('activated_specialists')}")
                logger.info(f"State keys: {list(new_state.keys())}")
                logger.info(f"Current step: {new_state.get('current_step')}")
                logger.info(f"About to return from TRIAGE node - conditional edge should be called next")
                
            else:
                error_msg = f"TRIAGE agent failed: {result.get('error', 'Unknown error')}"
                new_state["error_message"] = error_msg
                # Установка значений по умолчанию
                new_state["urgency_level"] = UrgencyLevel.ROUTINE
                new_state["activated_specialists"] = ["INFECTION"]  # По умолчанию в верхнем регистре
            
            return new_state
            
        except Exception as e:
            logger.error(f"TRIAGE node error: {str(e)}")
            new_state = state.copy()
            new_state["error_message"] = str(e)
            # Используем fallback данные при исключении
            fallback_data = self._get_fallback_triage_data(state)
            new_state["urgency_level"] = fallback_data.get("urgency_level", UrgencyLevel.ROUTINE)
            new_state["activated_specialists"] = fallback_data.get("activated_specialists", ["INFECTION"])
            return new_state
    
    @timing_decorator("hypothesis_generator")
    async def _hypothesis_generator_node(self, state: GraphState) -> GraphState:
        """Узел HYPOTHESIS_GENERATOR AGENT - генерация диагностических гипотез с расчетом уверенности"""
        logger.info("=== HYPOTHESIS_GENERATOR NODE STARTED ===")
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Executing HYPOTHESIS_GENERATOR agent for session {session_id}")
        
        try:
            # Подготовка контекста
            context = {
                "patient_data": state["patient_data"],
                "data_completeness_output": state.get("data_completeness_checker_output", {}),
                "triage_output": state.get("triage_output", {}),
                "current_confidence": state.get("diagnostic_confidence", 0.0),
                "questions_asked": state.get("questions_asked_count", 0)
            }
            
            # Вызов агента
            client = await get_ai_studio_client()
            result = await client.call_agent(
                agent_name="hypothesis_generator",
                prompt="Сгенерируй диагностические гипотезы с расчетом уверенности",
                context=context
            )
            
            # Создаем новое состояние
            new_state = state.copy()
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                
                # Обновление гипотез
                new_state["hypotheses"] = parsed_data.get("hypotheses", [])
                new_state["most_likely_diagnosis"] = parsed_data.get("most_likely_diagnosis")
                new_state["key_discriminators"] = parsed_data.get("key_discriminators", [])
                
                # Извлечение и обновление диагностической уверенности
                overall_confidence = _coerce_unit_interval(
                    parsed_data.get("overall_diagnostic_confidence", 0.0), 0.0
                )
                if overall_confidence > 0:
                    new_state = update_diagnostic_confidence(
                        new_state,
                        overall_confidence,
                        f"Hypothesis generator calculated confidence based on {len(new_state['hypotheses'])} hypotheses"
                    )
                    logger.info(
                        f"Updated diagnostic confidence to {overall_confidence:.2f} from hypothesis generator"
                    )
                
                # Обновление сложности случая на основе гипотез
                if not new_state.get("case_complexity") or new_state["case_complexity"] == "medium":
                    # Анализируем гипотезы для определения сложности
                    high_risk_diagnoses = ["лейкоз", "лимфома", "сепсис", "менингит", "системное заболевание"]
                    complexity_score = 0
                    
                    for hypothesis in new_state["hypotheses"]:
                        diagnosis = hypothesis.get("diagnosis", "").lower()
                        if any(risk in diagnosis for risk in high_risk_diagnoses):
                            complexity_score += 2
                        elif hypothesis.get("probability") == "низкая":
                            complexity_score += 1
                    
                    if complexity_score >= 3:
                        new_state["case_complexity"] = "high"
                        new_state["max_questions_allowed"] = calculate_max_questions("high")
                    elif complexity_score >= 1:
                        new_state["case_complexity"] = "medium"
                        new_state["max_questions_allowed"] = calculate_max_questions("medium")
                    else:
                        new_state["case_complexity"] = "low"
                        new_state["max_questions_allowed"] = calculate_max_questions("low")
                    
                    logger.info(f"Updated case complexity to {new_state['case_complexity']} (score: {complexity_score})")
                
                # Обновление состояния
                new_state["current_step"] = "hypothesis_generation_completed"
                
                # Добавление результата агента
                new_state = add_agent_output(
                    new_state,
                    "hypothesis_generator",
                    parsed_data,
                    confidence=1.0,
                    execution_time_ms=result.get("execution_time_ms")
                )
                
                # Добавление ответа агента с информацией об уверенности
                hypotheses = new_state["hypotheses"]
                most_likely = new_state["most_likely_diagnosis"]
                confidence = _coerce_unit_interval(new_state.get("diagnostic_confidence"), 0.0)
                confidence_threshold = _coerce_unit_interval(
                    new_state.get("confidence_threshold", 0.85), 0.85
                )
                
                response_text = "🔍 ДИФФЕРЕНЦИАЛЬНАЯ ДИАГНОСТИКА\n\n"
                
                # Добавляем информацию об уверенности
                response_text += f"📊 Диагностическая уверенность: {confidence:.1%}\n"
                if confidence >= confidence_threshold:
                    response_text += "✅ Достаточная уверенность для постановки диагноза\n\n"
                else:
                    response_text += f"⚠️ Требуется больше информации для достижения порога {confidence_threshold:.1%}\n\n"
                
                if most_likely:
                    response_text += f"🎯 Наиболее вероятный диагноз: {most_likely}\n\n"
                
                if hypotheses:
                    response_text += "📋 Основные гипотезы:\n"
                    for i, hypothesis in enumerate(hypotheses[:3], 1):  # Показываем топ-3
                        diagnosis = hypothesis.get("diagnosis", "Неизвестно")
                        probability = hypothesis.get("probability", "Низкая")
                        confidence_contrib = _coerce_unit_interval(
                            hypothesis.get("confidence_contribution", 0.0), 0.0
                        )
                        response_text += (
                            f"{i}. {diagnosis} (вероятность: {probability}, "
                            f"вклад в уверенность: {confidence_contrib:.1%})\n"
                        )
                    response_text += "\n"
                
                if new_state["key_discriminators"]:
                    response_text += f"🔑 Ключевые дифференциальные признаки: {', '.join(new_state['key_discriminators'][:3])}\n"
                
                # Добавляем информацию о следующих шагах
                additional_questions = parsed_data.get("additional_questions_needed", [])
                if additional_questions and confidence < confidence_threshold:
                    response_text += f"\n📝 Для повышения уверенности рекомендуется уточнить: {', '.join(additional_questions[:2])}"
                
                new_state = add_message(new_state, "assistant", response_text)
                
                logger.info(f"HYPOTHESIS_GENERATOR completed: hypotheses={len(hypotheses)}, most_likely={most_likely}, confidence={confidence:.2f}")
                
            else:
                error_msg = f"HYPOTHESIS_GENERATOR agent failed: {result.get('error', 'Unknown error')}"
                new_state["error_message"] = error_msg
                # Установка значений по умолчанию
                new_state["hypotheses"] = []
                new_state["most_likely_diagnosis"] = None
                new_state["key_discriminators"] = []
                logger.warning(error_msg)
            
            return new_state
            
        except Exception as e:
            logger.error(f"HYPOTHESIS_GENERATOR node error: {str(e)}")
            new_state = state.copy()
            new_state["error_message"] = str(e)
            new_state["hypotheses"] = []
            new_state["most_likely_diagnosis"] = None
            new_state["key_discriminators"] = []
            return new_state
    
    async def _question_node(self, state: GraphState) -> GraphState:
        """Узел QUESTION AGENT - динамическое формирование вопросов с учетом уверенности"""
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Executing QUESTION agent for session {session_id}")
        
        try:
            # Получаем параметры состояния
            dialogue_phase = state.get("dialogue_phase", "gathering_info")
            questions_asked_count = state.get("questions_asked_count", 0)
            diagnostic_confidence = state.get("diagnostic_confidence", 0.0)
            confidence_threshold = state.get("confidence_threshold", 0.85)
            max_questions_allowed = state.get("max_questions_allowed", 10)
            case_complexity = state.get("case_complexity", "medium")
            
            # Динамическая оценка необходимости вопросов
            question_priority = calculate_question_priority(state)
            estimated_gain = estimate_confidence_gain(state)
            
            # Проверяем, следует ли продолжать задавать вопросы
            if not should_continue_questions(state):
                logger.info(f"QUESTION node: Stopping questions - confidence: {diagnostic_confidence:.2f}, asked: {questions_asked_count}, priority: {question_priority}")
                new_state = state.copy()
                new_state["dialogue_phase"] = "diagnosis"
                new_state["awaiting_user_response"] = False
                new_state["needs_more_info"] = False
                
                # Формируем сообщение о завершении сбора информации (дальше — тяжёлый пайплайн: триаж, гипотезы, специалисты, синтез)
                _analysis_notice = (
                    "\n\n"
                    "⏱ Ориентировочно 1–3 минуты на полный цикл анализа (зависит от нагрузки и сложности случая).\n"
                    "Сейчас по очереди выполняется: оценка срочности (триаж) → гипотезы → "
                    "при необходимости узкие специалисты → сводка и рекомендации. "
                    "Дождитесь сообщения с результатом; страницу обновлять не нужно."
                )
                if diagnostic_confidence >= confidence_threshold:
                    response_text = (
                        f"✅ Достигнута достаточная уверенность в диагнозе ({diagnostic_confidence:.1%}). "
                        f"Переходим к анализу.{_analysis_notice}"
                    )
                else:
                    response_text = (
                        f"📊 Собрано достаточно информации для анализа. Уверенность: {diagnostic_confidence:.1%}. "
                        f"Переходим к диагностике.{_analysis_notice}"
                    )
                
                new_state = add_message(new_state, "assistant", response_text)
                new_state["current_step"] = "questions_completed"
                return new_state
            
            # Если мы не в фазе сбора информации, пропускаем
            if dialogue_phase != "gathering_info":
                new_state = state.copy()
                new_state["current_step"] = "questions_skipped"
                return new_state
            
            # Создаем новое состояние
            new_state = state.copy()
            
            # Адаптивный режим: каждый вызов — новый вопрос по актуальным данным и диалогу
            # (пул с прошлого шага сбрасывается в intake после ответа пользователя).
            logger.info("QUESTION node: generating next adaptive question (single-turn)")
            
            # Определяем сложность случая, если не установлена
            if case_complexity == "medium" and len(state.get("red_flags_identified", [])) > 0:
                case_complexity = calculate_case_complexity(
                    state["patient_data"],
                    state.get("red_flags_identified", [])
                )
                new_state["case_complexity"] = case_complexity
                new_state["max_questions_allowed"] = calculate_max_questions(case_complexity)
            
            # Подготовка контекста с учетом уверенности и динамической оценки
            _pd = state.get("patient_data") or {}
            _labs = _pd.get("lab_results") or {}
            _has_labs = bool(
                _labs
                if isinstance(_labs, dict)
                else (isinstance(_labs, str) and _labs.strip())
            )
            context = {
                "current_hypotheses": {
                    "urgency_level": state["urgency_level"],
                    "activated_specialists": state["activated_specialists"],
                    "diagnostic_confidence": diagnostic_confidence,
                    "confidence_threshold": confidence_threshold
                },
                "missing_data": {
                    "patient_data": state["patient_data"],
                    "missing_info": state["patient_data"].get("missing_info", []),
                    "has_structured_lab_results": _has_labs,
                    "lab_results_summary": _labs if isinstance(_labs, dict) else {},
                },
                "question_constraints": {
                    "max_questions": max_questions_allowed,
                    "questions_asked": questions_asked_count,
                    "remaining_questions": max_questions_allowed - questions_asked_count,
                    "case_complexity": case_complexity
                },
                "dynamic_assessment": {
                    "question_priority": question_priority,
                    "estimated_confidence_gain": estimated_gain,
                    "confidence_gap": confidence_threshold - diagnostic_confidence
                },
                "recent_dialogue": _recent_dialogue_for_question(state),
                "adaptive_questions": True,
                "dialogue_mode": True,
                "message_count": len(state.get("messages", [])),
                "questions_asked_so_far": questions_asked_count,
            }
            
            # Вызов агента: один следующий вопрос с учётом последних реплик
            client = await get_ai_studio_client()
            result = await client.call_agent(
                agent_name="question",
                prompt=(
                    f"Сформируй ровно один следующий уточняющий вопрос с учётом последних реплик диалога "
                    f"и новых данных пациента. Не повторяй уже отвеченное. "
                    f"Уверенность: {diagnostic_confidence:.1%}, сложность: {case_complexity}."
                ),
                context=context
            )
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                raw_questions = parsed_data.get("questions", [])
                # Берём только первый вопрос (модель может вернуть несколько)
                questions = raw_questions[:1]
                if len(raw_questions) > 1:
                    parsed_data = {**parsed_data, "questions": questions[:1]}
                
                if questions:
                    new_state["questions_to_ask"] = questions
                    new_state["needs_more_info"] = True
                    new_state["current_step"] = "questions_generated"
                    new_state["awaiting_user_response"] = True
                    
                    new_state = add_agent_output(
                        new_state,
                        "question",
                        parsed_data,
                        confidence=1.0,
                        execution_time_ms=result.get("execution_time_ms")
                    )
                    
                    current_question = questions[0]
                    response_text = current_question.get("question", "")
                    
                    question_lower = response_text.lower()
                    medical_explanations = []
                    
                    if "кашель" in question_lower and ("сухой" in question_lower or "влажный" in question_lower):
                        medical_explanations.append(
                            "💡 **Справка:** Сухой кашель - без мокроты, часто раздражающий. "
                            "Влажный кашель - с отделением мокроты (слизи)."
                        )
                    
                    if "лихорадка" in question_lower or "тип лихорадки" in question_lower:
                        medical_explanations.append(
                            "💡 **Справка:** Лихорадка - повышение температуры тела выше нормы. "
                            "Типы: постоянная (температура стабильна), ремиттирующая (колеблется), "
                            "интермиттирующая (периоды нормальной температуры)."
                        )
                    
                    if current_question.get("explanation"):
                        medical_explanations.append(f"_{current_question['explanation']}_")
                    
                    if medical_explanations:
                        response_text += "\n\n" + "\n\n".join(medical_explanations)
                    
                    new_state["current_question_index"] = 1
                    new_state["questions_asked_count"] = questions_asked_count + 1
                    
                    logger.info(
                        f"QUESTION node: adaptive question generated (total asked: {questions_asked_count + 1})"
                    )
                else:
                    new_state["dialogue_phase"] = "diagnosis"
                    new_state["awaiting_user_response"] = False
                    new_state["needs_more_info"] = False
                    response_text = "Спасибо за информацию. Теперь я проанализирую полученные данные."
                    
                    logger.info("QUESTION node: No questions generated, moving to diagnosis")
            else:
                error_msg = f"QUESTION agent failed: {result.get('error', 'Unknown error')}"
                new_state["error_message"] = error_msg
                response_text = "Не удалось сформировать вопросы. Продолжаем с имеющимися данными."
                new_state["needs_more_info"] = False
                logger.warning(f"QUESTION node failed: {error_msg}")
            
            new_state = add_message(new_state, "assistant", response_text)
            new_state["last_agent_executed"] = "question"
            
            return new_state
            
        except Exception as e:
            logger.error(f"QUESTION node error: {str(e)}")
            new_state = state.copy()
            new_state["error_message"] = str(e)
            new_state["needs_more_info"] = False
            new_state["last_agent_executed"] = "question"
            return new_state
    
    async def _execute_hypothesis_parallel(self, state: GraphState) -> GraphState:
        """Запуск hypothesis_generator без добавления сообщений — для параллельного выполнения."""
        logger.info("=== HYPOTHESIS_GENERATOR (PARALLEL) STARTED ===")
        try:
            context = {
                "patient_data": state["patient_data"],
                "data_completeness_output": state.get("data_completeness_checker_output", {}),
                "triage_output": state.get("triage_output", {}),
                "current_confidence": state.get("diagnostic_confidence", 0.0),
                "questions_asked": state.get("questions_asked_count", 0),
            }
            client = await get_ai_studio_client()
            result = await client.call_agent(
                agent_name="hypothesis_generator",
                prompt="Сгенерируй диагностические гипотезы с расчетом уверенности",
                context=context,
            )
            new_state = state.copy()
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                new_state["hypotheses"] = parsed_data.get("hypotheses", [])
                new_state["most_likely_diagnosis"] = parsed_data.get("most_likely_diagnosis")
                new_state["key_discriminators"] = parsed_data.get("key_discriminators", [])
                overall_confidence = _coerce_unit_interval(
                    parsed_data.get("overall_diagnostic_confidence", 0.0), 0.0
                )
                if overall_confidence > 0:
                    new_state = update_diagnostic_confidence(
                        new_state, overall_confidence,
                        f"Hypothesis generator: {len(new_state['hypotheses'])} hypotheses"
                    )
                # Обновляем сложность случая на основе гипотез
                high_risk = ["лейкоз", "лимфома", "сепсис", "менингит", "системное заболевание"]
                score = sum(
                    2 if any(r in h.get("diagnosis", "").lower() for r in high_risk)
                    else (1 if h.get("probability") == "низкая" else 0)
                    for h in new_state["hypotheses"]
                )
                complexity = "high" if score >= 3 else ("medium" if score >= 1 else "low")
                new_state["case_complexity"] = complexity
                new_state["max_questions_allowed"] = calculate_max_questions(complexity)
                new_state = add_agent_output(
                    new_state, "hypothesis_generator", parsed_data,
                    confidence=1.0, execution_time_ms=result.get("execution_time_ms")
                )
                increment_cost_units(new_state)
                logger.info(f"HYPOTHESIS_GENERATOR (parallel) completed: {len(new_state['hypotheses'])} hypotheses")
            else:
                logger.warning(f"HYPOTHESIS_GENERATOR (parallel) failed: {result.get('error')}")
                new_state["hypotheses"] = new_state.get("hypotheses") or []
                new_state["most_likely_diagnosis"] = new_state.get("most_likely_diagnosis")
                new_state["key_discriminators"] = new_state.get("key_discriminators") or []
            return new_state
        except Exception as e:
            logger.error(f"_execute_hypothesis_parallel error: {e}")
            new_state = state.copy()
            new_state["hypotheses"] = new_state.get("hypotheses") or []
            return new_state

    async def _route_to_specialists_node(self, state: GraphState) -> GraphState:
        """Узел маршрутизации к специалистам - запускает всех активированных специалистов параллельно"""
        logger.info("=== ROUTE_TO_SPECIALISTS NODE STARTED ===")
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Executing route_to_specialists for session {session_id}")
        
        activated_specialists = state.get("activated_specialists", [])
        logger.info(f"Activated specialists: {activated_specialists}")
        
        new_state = state.copy()
        new_state["current_step"] = "routing_to_specialists"
        
        # Если нет активированных специалистов, переходим к synthesis
        if not activated_specialists:
            logger.info("No activated specialists, going directly to synthesis")
            return new_state
        
        # Проверяем, не были ли уже выполнены специалисты (для обратной совместимости)
        if new_state.get("specialists_executed", False):
            logger.info("Specialists already executed, skipping parallel execution")
            return new_state

        # Budgeted режим: пропускаем специалистов если лимит исчерпан
        if state.get("run_mode") == "budgeted":
            max_units = state.get("max_cost_units")
            used_units = state.get("total_cost_units", 0)
            if max_units is not None and used_units >= max_units:
                logger.info(f"Budget exhausted ({used_units}/{max_units}), skipping specialists")
                return new_state
        
        # Запускаем hypothesis_generator и всех специалистов параллельно
        specialist_mapping = {
            "INFECTION": "infection",
            "IMMUNE": "immune",
            "ONCOLOGY": "oncology",
            "RARE": "rare_disease",
            "RARE_DISEASE": "rare_disease",
        }

        tasks: list = []
        task_names: list = []

        # Включаем hypothesis_generator, если он ещё не выполнен
        if not state.get("hypothesis_generator_output"):
            tasks.append(self._execute_hypothesis_parallel(state))
            task_names.append("hypothesis_generator")

        for specialist in activated_specialists:
            key = specialist.upper() if isinstance(specialist, str) else str(specialist).upper()
            if key in specialist_mapping:
                agent_name = specialist_mapping[key]
                task_names.append(agent_name)
                tasks.append(self._execute_specialist_node_parallel(agent_name, state))

        logger.info(
            f"Starting parallel execution: {task_names} "
            f"({len(tasks)} tasks)"
        )
        start_time = datetime.now()

        try:
            # Таймаут 120с — чтобы зависший LLM-вызов не блокировал граф бесконечно
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=120.0,
            )

            for name, result in zip(task_names, results):
                if isinstance(result, Exception):
                    logger.error(f"Parallel task '{name}' failed: {result}")
                    new_state = add_agent_output(
                        new_state, name, {"error": str(result)}, confidence=0.0
                    )
                    continue
                if not isinstance(result, dict):
                    logger.warning(f"Parallel task '{name}' returned unexpected type: {type(result)}")
                    continue

                # Копируем только output конкретного агента (не перезаписываем messages)
                output_key = f"{name}_output"
                if output_key in result:
                    new_state[output_key] = result[output_key]

                # Для hypothesis_generator дополнительно переносим расчётные поля
                if name == "hypothesis_generator":
                    for key in (
                        "hypotheses", "most_likely_diagnosis", "key_discriminators",
                        "diagnostic_confidence", "case_complexity", "max_questions_allowed",
                    ):
                        if result.get(key) is not None:
                            new_state[key] = result[key]

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"Parallel execution completed in {execution_time:.2f}ms")
            new_state["specialists_executed"] = True
            new_state["specialists_execution_time_ms"] = int(execution_time)

        except asyncio.TimeoutError:
            logger.error("Parallel diagnosis timed out after 120s — proceeding to synthesis with partial results")
            new_state["error_message"] = "Parallel diagnosis timed out"
            new_state["specialists_executed"] = True
        except Exception as e:
            logger.error(f"Error in parallel execution: {e}")
            new_state["error_message"] = f"Error executing parallel diagnosis: {e}"
        
        logger.info("About to return from route_to_specialists")
        return new_state
    
    async def _execute_specialist_node_parallel(self, agent_name: str, state: GraphState) -> GraphState:
        """Выполнение узла специалиста для параллельного запуска (без добавления сообщений)"""
        logger.info(f"=== {agent_name.upper()} NODE (PARALLEL) STARTED ===")
        session_id = state.get('session_id', 'unknown')

        try:
            # Подготовка контекста — специалист видит триаж и гипотезы (1.4)
            context = {
                "patient_data": state["patient_data"],
                "triage_output": state.get("triage_output") or {},
                "hypotheses": state.get("hypotheses") or [],
                "most_likely_diagnosis": state.get("most_likely_diagnosis"),
            }

            # Вызов агента
            client = await get_ai_studio_client()
            result = await client.call_agent(
                agent_name=agent_name,
                prompt=f"Проведи анализ для {agent_name}",
                context=context
            )
            
            # Создаем новое состояние только с результатом агента (без сообщений)
            new_state = state.copy()
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                
                # Добавление результата агента
                new_state = add_agent_output(
                    new_state,
                    agent_name,
                    parsed_data,
                    confidence=1.0,
                    execution_time_ms=result.get("execution_time_ms")
                )
                increment_cost_units(new_state)
                logger.info(f"{agent_name.upper()} agent completed successfully")
            else:
                error_msg = f"{agent_name.upper()} agent failed: {result.get('error', 'Unknown error')}"
                new_state = add_agent_output(
                    new_state,
                    agent_name,
                    {"error": error_msg},
                    confidence=0.0
                )
                logger.warning(error_msg)
            
            return new_state
            
        except Exception as e:
            logger.error(f"{agent_name.upper()} node (parallel) error: {str(e)}")
            new_state = state.copy()
            new_state = add_agent_output(
                new_state,
                agent_name,
                {"error": str(e)},
                confidence=0.0
            )
        return new_state
    
    @timing_decorator("infection")
    async def _infection_node(self, state: GraphState) -> GraphState:
        """Узел INFECTION AGENT - анализ инфекционных причин"""
        return await self._execute_specialist_node("infection", state)
    
    @timing_decorator("immune")
    async def _immune_node(self, state: GraphState) -> GraphState:
        """Узел IMMUNE AGENT - анализ аутоиммунных причин"""
        return await self._execute_specialist_node("immune", state)
    
    @timing_decorator("oncology")
    async def _oncology_node(self, state: GraphState) -> GraphState:
        """Узел ONCOLOGY AGENT - анализ онкологических причин"""
        return await self._execute_specialist_node("oncology", state)
    
    @timing_decorator("rare_disease")
    async def _rare_disease_node(self, state: GraphState) -> GraphState:
        """Узел RARE DISEASE AGENT - анализ редких заболеваний"""
        return await self._execute_specialist_node("rare_disease", state)
    
    async def _execute_specialist_node(self, agent_name: str, state: GraphState) -> GraphState:
        """Общий метод для выполнения узлов специалистов"""
        logger.info(f"=== {agent_name.upper()} NODE STARTED ===")
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Executing {agent_name.upper()} agent for session {session_id}")
        logger.info(f"State type: {type(state)}")
        logger.info(f"State keys: {list(state.keys())}")
        
        try:
            # Подготовка контекста
            context = {
                "patient_data": state["patient_data"]
            }
            
            # Вызов агента
            client = await get_ai_studio_client()
            result = await client.call_agent(
                agent_name=agent_name,
                prompt=f"Проведи анализ для {agent_name}",
                context=context
            )
            
            # Создаем новое состояние
            new_state = state.copy()
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                
                # Добавление результата агента
                new_state = add_agent_output(
                    new_state,
                    agent_name,
                    parsed_data,
                    confidence=1.0,
                    execution_time_ms=result.get("execution_time_ms")
                )
                
                # Добавление краткого ответа
                if agent_name == "infection":
                    most_likely = parsed_data.get("most_likely", "Не определено")
                    response_text = f"Инфекционный анализ: наиболее вероятный диагноз - {most_likely}"
                elif agent_name == "immune":
                    conditions = parsed_data.get("relevant_conditions", [])
                    response_text = f"Иммунологический анализ: {', '.join(conditions[:3])}"
                elif agent_name == "oncology":
                    risk = parsed_data.get("oncological_risk", "low")
                    response_text = f"Онкологический риск: {risk}"
                elif agent_name == "rare_disease":
                    diagnoses = parsed_data.get("rare_diagnoses_to_consider", [])
                    response_text = f"Редкие заболевания: {', '.join(diagnoses[:2])}"
                else:
                    response_text = f"{agent_name.upper()} анализ завершен"
                
                new_state = add_message(new_state, "assistant", response_text)
                logger.info(f"{agent_name.upper()} agent completed successfully")
                
            else:
                error_msg = f"{agent_name.upper()} agent failed: {result.get('error', 'Unknown error')}"
                new_state["error_message"] = error_msg
                logger.warning(error_msg)
            
            logger.info(f"About to return from {agent_name.upper()} node")
            return new_state
            
        except Exception as e:
            logger.error(f"{agent_name.upper()} node error: {str(e)}")
            new_state = state.copy()
            new_state["error_message"] = str(e)
            return new_state
    
    @timing_decorator("synthesis")
    async def _synthesis_node(self, state: GraphState) -> GraphState:
        """Узел SYNTHESIS AGENT - формирование финальных рекомендаций"""
        logger.info("=== SYNTHESIS NODE STARTED ===")
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Executing SYNTHESIS agent for session {session_id}")
        logger.info(f"State type: {type(state)}")
        logger.info(f"State keys: {list(state.keys())}")
        
        try:
            # Проверка на простой случай
            is_simple_case = state.get("is_simple_case", False)
            
            # Сбор всех результатов агентов
            all_outputs = {}
            for agent_name in ["intake", "triage"]:
                output = state.get(f"{agent_name}_output")
                if output:
                    all_outputs[agent_name] = output
            
            # Для простых случаев не включаем результаты специалистов и гипотез
            if not is_simple_case:
                for agent_name in ["infection", "immune", "oncology", "rare_disease"]:
                    output = state.get(f"{agent_name}_output")
                    if output:
                        all_outputs[agent_name] = output
                
                # Добавляем гипотезы если есть
                hypotheses = state.get("hypotheses", [])
                if hypotheses:
                    all_outputs["hypotheses"] = hypotheses
            
            logger.info(f"Collected outputs from {len(all_outputs)} agents: {list(all_outputs.keys())}")
            if is_simple_case:
                logger.info("Simple case: synthesis will work with intake and triage only")
            
            # Подготовка контекста
            context = {
                "all_agent_outputs": all_outputs,
                "patient_data": state["patient_data"],
                "urgency_level": state["urgency_level"]
            }
            
            # Вызов агента
            client = await get_ai_studio_client()
            result = await client.call_agent(
                agent_name="synthesis",
                prompt="Сформируй финальные рекомендации с маршрутизацией",
                context=context
            )
            
            # Создаем новое состояние
            new_state = state.copy()
            
            if result.get("success") and result.get("parsed_data"):
                parsed_data = result["parsed_data"]
                
                # Извлечение возможных диагнозов
                possible_diagnoses = parsed_data.get("possible_diagnoses", [])
                if possible_diagnoses:
                    new_state["possible_diagnoses"] = possible_diagnoses
                    logger.info(f"Extracted {len(possible_diagnoses)} possible diagnoses")
                
                # Обновление рекомендаций
                primary_specialist = parsed_data.get("primary_specialist")
                additional_specialists = parsed_data.get("additional_specialists", [])
                
                # Фильтрация специалистов по возрасту пациента
                patient_age_years = state.get("patient_data", {}).get("age_years")
                patient_age_months = state.get("patient_data", {}).get("age_months")
                
                # Неонатолог только для детей до 1 месяца (28 дней)
                if patient_age_years is not None or patient_age_months is not None:
                    age_in_days = 0
                    if patient_age_months is not None:
                        age_in_days = patient_age_months * 30  # Приблизительно
                    elif patient_age_years is not None:
                        age_in_days = patient_age_years * 365
                    
                    # Фильтруем неонатолога для детей старше 1 месяца
                    if age_in_days > 28:
                        # Удаляем неонатолога из списка специалистов
                        if primary_specialist and isinstance(primary_specialist, dict):
                            if primary_specialist.get("specialty", "").upper() in ["NEONATOLOGIST", "НЕОНАТОЛОГ"]:
                                primary_specialist = None
                                logger.info(f"Removed neonatologist for patient older than 1 month (age: {age_in_days} days)")
                        
                        additional_specialists = [
                            spec for spec in additional_specialists
                            if isinstance(spec, dict) and spec.get("specialty", "").upper() not in ["NEONATOLOGIST", "НЕОНАТОЛОГ"]
                        ]
                
                # Проверка на повторяющиеся эпизоды лихорадки для рекомендации иммунолога
                patient_data = state.get("patient_data", {})
                anamnesis = patient_data.get("anamnesis", {})
                additional_info = patient_data.get("additional_info", "")
                
                # Проверяем наличие повторяющихся эпизодов лихорадки
                has_recurrent_fever = False
                fever_episodes_count = 0
                
                # Проверяем в анамнезе
                if isinstance(anamnesis, dict):
                    past_episodes = anamnesis.get("past_fever_episodes", [])
                    if isinstance(past_episodes, list) and len(past_episodes) >= 4:
                        has_recurrent_fever = True
                        fever_episodes_count = len(past_episodes)
                
                # Проверяем в дополнительной информации (текстовый поиск)
                if additional_info:
                    import re
                    # Ищем упоминания о повторяющихся эпизодах
                    patterns = [
                        r'(\d+)\s*(?:раз|раза|эпизод)',
                        r'повторяющ',
                        r'регулярн',
                        r'част',
                    ]
                    for pattern in patterns:
                        if re.search(pattern, additional_info.lower()):
                            has_recurrent_fever = True
                            break
                
                # Проверяем наличие в анамнезе пневмонии или отитов
                has_pneumonia_history = False
                has_otitis_history = False
                
                if isinstance(anamnesis, dict):
                    past_illnesses = anamnesis.get("past_illnesses", [])
                    if isinstance(past_illnesses, list):
                        for illness in past_illnesses:
                            illness_lower = str(illness).lower()
                            if "пневмония" in illness_lower or "pneumonia" in illness_lower:
                                has_pneumonia_history = True
                            if "отит" in illness_lower or "otitis" in illness_lower:
                                has_otitis_history = True
                
                # Если есть повторяющиеся эпизоды (4+ раза за 6 месяцев) и история пневмонии/отитов
                if has_recurrent_fever and (has_pneumonia_history or has_otitis_history):
                    # Проверяем, нет ли уже иммунолога в списке
                    has_immunologist = False
                    if primary_specialist and isinstance(primary_specialist, dict):
                        if "иммунолог" in primary_specialist.get("specialty", "").lower() or \
                           "IMMUNE" in primary_specialist.get("specialty", "").upper():
                            has_immunologist = True
                    
                    for spec in additional_specialists:
                        if isinstance(spec, dict):
                            if "иммунолог" in spec.get("specialty", "").lower() or \
                               "IMMUNE" in spec.get("specialty", "").upper():
                                has_immunologist = True
                                break
                    
                    if not has_immunologist:
                        # Добавляем иммунолога в список дополнительных специалистов
                        immunologist_spec = {
                            "name": "Иммунолог",
                            "specialty": "Иммунолог",
                            "reasons": [
                                f"Повторяющиеся эпизоды лихорадки ({fever_episodes_count if fever_episodes_count > 0 else 'множественные'} раз)",
                                "Наличие в анамнезе пневмонии или отитов" if has_pneumonia_history or has_otitis_history else "Повторяющиеся инфекции"
                            ],
                            "priority": "high",
                            "timeframe": "В ближайшее время",
                            "purpose": "Исключение иммунодефицитных состояний"
                        }
                        additional_specialists.append(immunologist_spec)
                        logger.info("Added immunologist to recommendations due to recurrent fever episodes")
                
                new_state["primary_specialist"] = primary_specialist
                new_state["additional_specialists"] = additional_specialists
                new_state["required_tests"] = parsed_data.get("required_tests", [])
                new_state["red_flags"] = parsed_data.get("red_flags", [])
                new_state["recommendations_text"] = parsed_data.get("recommendations_text")
                new_state["current_step"] = "synthesis_completed"
                new_state["awaiting_user_response"] = False  # Сбрасываем флаг после синтеза
                new_state["needs_more_info"] = False  # Сбрасываем флаг после синтеза
                
                # Добавление результата агента
                new_state = add_agent_output(
                    new_state,
                    "synthesis",
                    parsed_data,
                    confidence=1.0,
                    execution_time_ms=result.get("execution_time_ms")
                )
                increment_cost_units(new_state)
                
                # Опциональная клиническая оценка (LLM-as-a-Judge, MAI-DxO-подобный Judge)
                if getattr(settings, "enable_clinical_eval", False):
                    try:
                        from app.core.llm_judge import evaluate_with_llm_judge, CRITERION_CLINICAL_APPROPRIATENESS
                        input_text = str(state.get("patient_data", {}))[:1500]
                        output_text = new_state.get("recommendations_text") or str(parsed_data)[:2000]
                        judge_result = await evaluate_with_llm_judge(
                            input_text, output_text, "synthesis", CRITERION_CLINICAL_APPROPRIATENESS
                        )
                        new_state["clinical_score"] = judge_result.score
                        logger.info(f"Clinical eval score: {judge_result.score}")
                    except Exception as e:
                        logger.warning(f"Clinical eval failed: {e}")
                
                # Формирование финального ответа
                primary = new_state["primary_specialist"]
                response_text = "🏥 РЕКОМЕНДАЦИИ ПО МАРШРУТИЗАЦИИ\n\n"
                response_text += f"📊 Уровень срочности: {parsed_data.get('urgency_level', 'routine').upper()}\n\n"
                response_text += f"👨‍⚕️ Основной специалист: {primary.get('name', 'Не определен')}\n"
                response_text += f"📋 Причины: {', '.join(primary.get('reasons', []))}\n\n"
                
                if new_state["additional_specialists"]:
                    response_text += "👥 Дополнительные консультации:\n"
                    for spec in new_state["additional_specialists"]:
                        response_text += f"• {spec.get('name', 'Не определен')}\n"
                    response_text += "\n"
                
                if new_state["required_tests"]:
                    response_text += "🧪 Рекомендуемые обследования:\n"
                    for test in new_state["required_tests"]:
                        response_text += f"• {test}\n"
                    response_text += "\n"
                
                response_text += f"📄 Полные рекомендации доступны в PDF отчете."
                
                new_state = add_message(new_state, "assistant", response_text)
                logger.info("SYNTHESIS agent completed successfully")
                
            else:
                error_msg = f"SYNTHESIS agent failed: {result.get('error', 'Unknown error')}"
                new_state["error_message"] = error_msg
                new_state = add_message(new_state, "assistant", "Не удалось сформировать рекомендации. Пожалуйста, обратитесь к врачу.")
                logger.warning(error_msg)
            
            logger.info("About to return from SYNTHESIS node")
            return new_state
            
        except Exception as e:
            logger.error(f"SYNTHESIS node error: {str(e)}")
            new_state = state.copy()
            new_state["error_message"] = str(e)
            new_state = add_message(new_state, "assistant", "Произошла ошибка при формировании рекомендаций.")
            return new_state
    
    async def _feedback_request_node(self, state: GraphState) -> GraphState:
        """Узел запроса обратной связи после рекомендаций"""
        logger.info("=== FEEDBACK REQUEST NODE STARTED ===")
        session_id = state.get('session_id', 'unknown')
        logger.info(f"Requesting feedback for session {session_id}")
        
        try:
            new_state = state.copy()
            
            # Проверяем, что рекомендации были сформированы
            if not state.get("synthesis_output"):
                logger.warning(f"No synthesis output for session {session_id}, skipping feedback request")
                return new_state
            
            # Проверяем, не была ли уже запрошена обратная связь
            if state.get("feedback_requested", False):
                logger.info(f"Feedback already requested for session {session_id}")
                return new_state
            
            # Формируем сообщение с запросом обратной связи
            feedback_message = "\n\n" + "="*50 + "\n"
            feedback_message += "📝 ОБРАТНАЯ СВЯЗЬ\n"
            feedback_message += "="*50 + "\n\n"
            feedback_message += "Помогите нам улучшить систему! Пожалуйста, ответьте на два вопроса:\n\n"
            feedback_message += "1. Была ли вам полезна эта рекомендация? (да/нет)\n"
            feedback_message += "2. Помогла ли она вам принять окончательное решение? (да/нет)\n\n"
            feedback_message += "Вы также можете оставить дополнительный комментарий, если хотите.\n"
            feedback_message += "Пример ответа: 'Да, была полезна. Да, помогла принять решение. Спасибо за помощь!'\n"
            
            new_state = add_message(new_state, "assistant", feedback_message)
            new_state["feedback_requested"] = True
            new_state["awaiting_user_response"] = True
            new_state["current_step"] = "feedback_requested"
            
            logger.info(f"Feedback request sent for session {session_id}")
            return new_state
            
        except Exception as e:
            logger.error(f"FEEDBACK_REQUEST node error: {str(e)}")
            # В случае ошибки просто возвращаем состояние без запроса обратной связи
            return state
    
    # Условные переходы
    
    def _after_data_check(self, state: GraphState) -> Literal["triage", "question"]:
        """Определяет дальнейший ход после проверки полноты данных
        
        СТРОГАЯ ЛОГИКА:
        - Требуется минимум 80% полноты данных для диагностики
        - Исключение: критические emergency случаи (можно начать с 70%)
        """
        
        logger.info("=== _after_data_check CALLED ===")
        logger.info(f"State type: {type(state)}")
        logger.info(f"State keys: {list(state.keys())}")
        
        # Проверяем фазу диалога
        dialogue_phase = state.get("dialogue_phase", "gathering_info")
        if dialogue_phase == "gathering_info":
            logger.info("_after_data_check: in gathering_info phase, asking questions")
            return "question"
        elif dialogue_phase == "diagnosis":
            # В фазе диагностики всегда продолжаем к triage
            logger.info("_after_data_check: in diagnosis phase, proceeding to triage")
            return "triage"
        
        data_completeness_score = state.get("data_completeness_score", 0)
        missing_critical_data = state.get("missing_critical_data", [])
        red_flags_identified = state.get("red_flags_identified", [])
        error_message = state.get("error_message")
        current_step = state.get("current_step", "unknown")
        
        logger.info(f"_after_data_check: score={data_completeness_score}, "
                    f"missing={missing_critical_data}, red_flags={red_flags_identified}")
        
        # Проверяем, что data_completeness_checker был выполнен
        if current_step != "data_check_completed":
            logger.warning(f"_after_data_check: data check not completed, current_step={current_step}")
            return "triage"  # Продолжаем к triage в любом случае
        
        # Критические emergency случаи с явной угрозой жизни
        critical_emergency_flags = [
            "нарушение сознания",
            "судороги",
            "дыхательная недостаточность",
            "геморрагическая сыпь",
            "невозможность разбудить"
        ]
        
        has_critical_emergency = any(
            flag.lower() in " ".join(red_flags_identified).lower()
            for flag in critical_emergency_flags
        )
        
        # EMERGENCY с критическими флагами: можно начать с 70%
        if has_critical_emergency and data_completeness_score >= 70:
            logger.info("_after_data_check: CRITICAL EMERGENCY - proceeding to triage with 70%+ data")
            return "triage"
        
        # Для всех остальных случаев: требуется минимум 80%
        if data_completeness_score >= 80:
            logger.info("_after_data_check: sufficient data (80%+), proceeding to triage")
            return "triage"
        
        # Если есть ошибки - задаем вопросы
        if error_message:
            logger.info("_after_data_check: returning 'question' due to error")
            return "question"
        
        # Если данных недостаточно - ВСЕГДА задаем вопросы
        logger.info(f"_after_data_check: insufficient data ({data_completeness_score}%), "
                    f"asking questions to collect: {missing_critical_data}")
        return "question"
    
    def _is_simple_case(self, state: GraphState) -> bool:
        """Проверка, является ли случай простым (можно пропустить hypothesis_generator и специалистов)
        
        Критерии простого случая:
        - triage_output.routine == True
        - confidence >= 0.9
        - data_completeness_score >= 0.8
        
        Args:
            state: Состояние графа
            
        Returns:
            True если случай простой
        """
        try:
            triage_output = state.get("triage_output") or {}
            urgency_level = state.get("urgency_level")
            data_completeness_score = state.get("data_completeness_score", 0)
            
            # Проверяем, что это routine случай
            is_routine = False
            if urgency_level:
                if hasattr(urgency_level, 'value'):
                    is_routine = urgency_level.value.upper() == "ROUTINE"
                else:
                    is_routine = str(urgency_level).upper() == "ROUTINE"
            
            # Проверяем уверенность (из triage_output или диагностическую)
            confidence = triage_output.get("confidence", state.get("diagnostic_confidence", 0.0))
            if isinstance(confidence, (int, float)):
                confidence_value = float(confidence)
            else:
                confidence_value = 0.0
            
            # Проверяем полноту данных (score хранится как 0-100, не 0.0-1.0)
            completeness_ok = data_completeness_score >= 80
            
            is_simple = is_routine and confidence_value >= 0.9 and completeness_ok
            
            if is_simple:
                logger.info(f"Simple case detected: routine={is_routine}, confidence={confidence_value:.2f}, completeness={data_completeness_score:.2f}")
            
            return is_simple
            
        except Exception as e:
            logger.warning(f"Error checking if case is simple: {str(e)}")
            return False
    
    def _should_continue_to_specialists(self, state: GraphState) -> Literal["hypothesis_generator", "specialists", "question", "synthesis", "end"]:
        """Определяет дальнейший ход после TRIAGE
        
        СТРОГАЯ ЛОГИКА:
        - Режим instant: сразу в synthesis (без специалистов и hypothesis_generator).
        - Даже после triage проверяем полноту данных
        - Если данных недостаточно - возвращаемся к вопросам (ТОЛЬКО в фазе gathering_info)
        - В фазе diagnosis всегда продолжаем к специалистам
        - Для простых случаев (routine, высокая уверенность) - пропускаем hypothesis_generator и идем к synthesis
        """
        
        logger.info("=== _should_continue_to_specialists CALLED ===")
        logger.info(f"State type: {type(state)}")
        logger.info(f"State keys: {list(state.keys())}")

        run_mode = state.get("run_mode", "full")
        if run_mode == "instant":
            logger.info("Run mode is 'instant': going directly to synthesis after triage")
            return "synthesis"

        activated_specialists = state.get("activated_specialists", [])
        error_message = state.get("error_message")
        current_step = state.get("current_step", "unknown")
        urgency_level = state.get("urgency_level")
        data_completeness_score = state.get("data_completeness_score", 0)
        missing_critical_data = state.get("missing_critical_data", [])
        dialogue_phase = state.get("dialogue_phase", "gathering_info")
        
        logger.info(f"_should_continue_to_specialists: specialists={activated_specialists}, "
                    f"score={data_completeness_score}, urgency={urgency_level}, phase={dialogue_phase}")
        
        # Проверяем, что TRIAGE был выполнен
        if current_step != "triage_completed":
            logger.warning(f"_should_continue_to_specialists: TRIAGE not completed, current_step={current_step}")
            return "end"
        
        # РАННЕЕ ЗАВЕРШЕНИЕ: проверка на простой случай
        if self._is_simple_case(state):
            logger.info("Simple case detected - skipping hypothesis_generator and specialists, going directly to synthesis")
            return "synthesis"
        
        # НОВАЯ ЛОГИКА: если мы в фазе diagnosis - всегда продолжаем к специалистам
        if dialogue_phase == "diagnosis":
            logger.info("_should_continue_to_specialists: in diagnosis phase, proceeding to parallel diagnosis")
            if activated_specialists and len(activated_specialists) > 0:
                return "specialists"
            return "end"
        
        # КРИТИЧЕСКАЯ ПРОВЕРКА: даже после triage проверяем полноту данных
        # Исключение только для критических emergency
        critical_emergency_flags = [
            "нарушение сознания",
            "судороги",
            "дыхательная недостаточность",
            "геморрагическая сыпь"
        ]
        
        red_flags = state.get("red_flags_identified", [])
        has_critical_emergency = any(
            flag.lower() in " ".join(red_flags).lower()
            for flag in critical_emergency_flags
        )
        
        # Для критических emergency: можно продолжить с 70%
        if has_critical_emergency and data_completeness_score >= 70:
            if activated_specialists and len(activated_specialists) > 0:
                logger.info("CRITICAL EMERGENCY: proceeding to parallel diagnosis with 70%+ data")
                return "specialists"
            return "end"
        
        # Для всех остальных в фазе gathering_info: требуется 80%
        if data_completeness_score < 80:
            logger.info(f"Insufficient data ({data_completeness_score}%), "
                        f"returning to questions before diagnosis")
            return "question"
        
        # Если данных достаточно и есть специалисты - запускаем параллельный анализ
        # hypothesis_generator выполнится параллельно со специалистами внутри route_to_specialists_node
        if activated_specialists and len(activated_specialists) > 0:
            logger.info(f"Sufficient data (80%+), proceeding to parallel diagnosis (hypothesis + specialists)")
            return "specialists"
        
        # Если есть ошибки - задаем вопросы
        if error_message:
            logger.info("_should_continue_to_specialists: returning 'question' due to error")
            return "question"
        
        # Если нет специалистов - задаем вопросы
        logger.info("No specialists activated, asking questions")
        return "question"
    
    def _should_continue_dialogue(self, state: GraphState) -> Literal["specialists", "question", "end"]:
        """Определяет дальнейший ход диалога после HYPOTHESIS_GENERATOR с учетом уверенности"""
        
        logger.info("=== _should_continue_dialogue CALLED ===")
        logger.info(f"State type: {type(state)}")
        logger.info(f"State keys: {list(state.keys())}")
        
        activated_specialists = state.get("activated_specialists", [])
        error_message = state.get("error_message")
        current_step = state.get("current_step", "unknown")
        urgency_level = state.get("urgency_level")
        hypotheses = state.get("hypotheses", [])
        diagnostic_confidence = state.get("diagnostic_confidence", 0.0)
        confidence_threshold = state.get("confidence_threshold", 0.85)
        questions_asked = state.get("questions_asked_count", 0)
        max_questions = state.get("max_questions_allowed", 10)
        dialogue_phase = state.get("dialogue_phase", "gathering_info")
        
        logger.info(f"_should_continue_dialogue: activated_specialists={activated_specialists}")
        logger.info(f"_should_continue_dialogue: error_message={error_message}")
        logger.info(f"_should_continue_dialogue: current_step={current_step}")
        logger.info(f"_should_continue_dialogue: urgency_level={urgency_level}")
        logger.info(f"_should_continue_dialogue: hypotheses count={len(hypotheses)}")
        logger.info(f"_should_continue_dialogue: confidence={diagnostic_confidence:.2f}, threshold={confidence_threshold}")
        logger.info(f"_should_continue_dialogue: questions={questions_asked}/{max_questions}, phase={dialogue_phase}")
        
        # Проверяем, что hypothesis_generator был выполнен
        if current_step != "hypothesis_generation_completed":
            logger.warning(f"_should_continue_dialogue: hypothesis generation not completed, current_step={current_step}")
            return "end"
        
        # Если мы в фазе диагностики - всегда продолжаем к специалистам
        if dialogue_phase == "diagnosis":
            if activated_specialists and len(activated_specialists) > 0:
                logger.info(f"_should_continue_dialogue: in diagnosis phase, routing to specialists: {activated_specialists}")
                return "specialists"
            else:
                logger.info("_should_continue_dialogue: in diagnosis phase but no specialists, ending")
                return "end"
        
        # Если достигнут порог уверенности - продолжаем к специалистам
        if diagnostic_confidence >= confidence_threshold:
            if activated_specialists and len(activated_specialists) > 0:
                logger.info(f"_should_continue_dialogue: confidence threshold reached, routing to specialists: {activated_specialists}")
                return "specialists"
            else:
                logger.info("_should_continue_dialogue: confidence threshold reached but no specialists, ending")
                return "end"
        
        # Если достигнут лимит вопросов - продолжаем к специалистам
        if questions_asked >= max_questions:
            if activated_specialists and len(activated_specialists) > 0:
                logger.info(f"_should_continue_dialogue: question limit reached, routing to specialists: {activated_specialists}")
                return "specialists"
            else:
                logger.info("_should_continue_dialogue: question limit reached but no specialists, ending")
                return "end"
        
        # Если есть активированные специалисты - продолжаем к специалистам
        if activated_specialists and len(activated_specialists) > 0:
            logger.info(f"_should_continue_dialogue: routing to specialists: {activated_specialists}")
            return "specialists"
        
        # Если есть ошибки - задаем вопросы
        if error_message:
            logger.info("_should_continue_dialogue: returning 'question' due to error")
            return "question"
        
        # Если есть гипотезы, но нет специалистов - задаем вопросы для уточнения
        if hypotheses and len(hypotheses) > 0:
            logger.info("_should_continue_dialogue: have hypotheses but no specialists, asking questions")
            return "question"
        
        # В остальных случаях - завершаем
        logger.info("_should_continue_dialogue: returning 'end' - no specialists activated")
        return "end"
    
    def _route_to_specialists(self, state: GraphState) -> str:
        """Маршрутизация к специализированным агентам
        
        После реализации параллельного выполнения, всегда возвращает "synthesis",
        так как все специалисты уже выполнены в _route_to_specialists_node
        
        Для простых случаев пропускает выполнение специалистов и идет напрямую к synthesis
        """
        # Проверяем, является ли это простым случаем
        if state.get("is_simple_case", False):
            logger.info("_route_to_specialists: simple case detected, skipping specialists, routing to synthesis")
            return "synthesis"
        
        # Проверяем, были ли уже выполнены специалисты параллельно
        if state.get("specialists_executed", False):
            logger.info("_route_to_specialists: specialists already executed in parallel, routing to synthesis")
            return "synthesis"
        
        # Для обратной совместимости (если параллельное выполнение не сработало)
        activated = state.get("activated_specialists", [])
        logger.info("=== _route_to_specialists CALLED ===")
        logger.info(f"_route_to_specialists: activated_specialists = {activated}")
        
        # Если нет активированных специалистов, идем к synthesis
        if not activated:
            logger.info("_route_to_specialists: no activated specialists, routing to synthesis")
            return "synthesis"
        
        # Приоритизация маршрутизации (fallback для последовательного выполнения)
        if "ONCOLOGY" in activated:
            logger.info("_route_to_specialists: routing to oncology (fallback)")
            return "oncology"
        elif "IMMUNE" in activated:
            logger.info("_route_to_specialists: routing to immune (fallback)")
            return "immune"
        elif "RARE" in activated or "RARE_DISEASE" in activated:
            logger.info("_route_to_specialists: routing to rare_disease (fallback)")
            return "rare_disease"
        elif "INFECTION" in activated:
            logger.info("_route_to_specialists: routing to infection (fallback)")
            return "infection"
        else:
            logger.warning(f"_route_to_specialists: no recognized specialists found in {activated}, routing to synthesis")
            return "synthesis"
    
    def _should_end_dialogue(self, state: GraphState) -> Literal["question", "end"]:
        """Продолжить диалог или завершить?"""
        # Если есть ошибки
        if state.get("error_message"):
            return "question"
        
        # Если рекомендации сформированы - всегда завершаем
        if state.get("synthesis_output"):
            return "end"
        
        # Если текущий шаг - синтез завершен, всегда завершаем
        if state.get("current_step") == "synthesis_completed":
            return "end"
        
        # Если ожидаем ответ пользователя - завершаем (ждем следующего сообщения)
        if state.get("awaiting_user_response"):
            return "end"
        
        # Если нужны уточнения (но только если еще не было синтеза)
        if state.get("needs_more_info") and not state.get("synthesis_output"):
            return "question"
        
        return "end"
    
    def _after_questions(self, state: GraphState) -> Literal["data_check", "end"]:
        """Определяет дальнейший ход после вопросов с учетом уверенности"""
        dialogue_phase = state.get("dialogue_phase", "gathering_info")
        diagnostic_confidence = state.get("diagnostic_confidence", 0.0)
        confidence_threshold = state.get("confidence_threshold", 0.85)
        questions_asked = state.get("questions_asked_count", 0)
        max_questions = state.get("max_questions_allowed", 10)
        
        # Если все вопросы заданы и мы переходим к диагностике
        if dialogue_phase == "diagnosis":
            logger.info(f"_after_questions: Moving to diagnosis (confidence: {diagnostic_confidence:.2f}, questions: {questions_asked}/{max_questions})")
            return "data_check"
        
        # Если достигнут порог уверенности - переходим к диагностике
        if diagnostic_confidence >= confidence_threshold:
            logger.info(f"_after_questions: Confidence threshold reached ({diagnostic_confidence:.2f} >= {confidence_threshold}), proceeding to data check")
            return "data_check"
        
        # Если достигнут лимит вопросов - переходим к диагностике
        if questions_asked >= max_questions:
            logger.info(f"_after_questions: Question limit reached ({questions_asked}/{max_questions}), proceeding to data check")
            return "data_check"
        
        # Если все еще в фазе сбора информации - завершаем (ждем следующего ответа)
        logger.info(f"_after_questions: Still gathering info (confidence: {diagnostic_confidence:.2f}, questions: {questions_asked}/{max_questions}), ending to wait for user response")
        return "end"
    
    # Вспомогательные методы
    
    def _validate_data_completeness_output(self, parsed_data: Dict[str, Any]) -> bool:
        """Валидация результата data_completeness_checker агента"""
        try:
            # Проверяем наличие обязательных полей
            required_fields = ["patient_data_complete", "data_completeness_score"]
            for field in required_fields:
                if field not in parsed_data:
                    return False
            
            # Проверяем типы и диапазоны
            if not isinstance(parsed_data["patient_data_complete"], bool):
                return False
            
            score = parsed_data["data_completeness_score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 100:
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error validating data_completeness output: {str(e)}")
            return False
    
    def _validate_agent_output(self, agent_name: str, parsed_data: Dict[str, Any]) -> bool:
        """Общая валидация результатов агентов"""
        try:
            if not parsed_data:
                return False
            
            # Базовая проверка на наличие данных
            if agent_name == "intake":
                # Проверяем наличие хотя бы одного поля данных пациента
                patient_fields = [
                    "patient_age",
                    "temperature",
                    "duration_days",
                    "symptoms",
                    "lab_results",
                    "anamnesis",
                    "physical_exam",
                ]
                return any(field in parsed_data for field in patient_fields)
            
            elif agent_name == "triage":
                # Проверяем наличие urgency_level
                return "urgency_level" in parsed_data or "activate_agents" in parsed_data
            
            elif agent_name == "synthesis":
                # Проверяем наличие рекомендаций
                return "primary_specialist" in parsed_data or "recommendations_text" in parsed_data
            
            # Для остальных агентов - базовая проверка на наличие данных
            return len(parsed_data) > 0
            
        except Exception as e:
            logger.error(f"Error validating {agent_name} output: {str(e)}")
            return False
    
    def _get_fallback_triage_data(self, state: GraphState) -> Dict[str, Any]:
        """Получение fallback данных для triage при ошибке агента
        
        Args:
            state: Состояние графа
            
        Returns:
            Базовые данные triage на основе данных пациента
        """
        from app.core.state import UrgencyLevel
        
        patient_data = state.get("patient_data", {})
        red_flags = patient_data.get("red_flags", [])
        temperature = patient_data.get("temperature_current", 0)
        age_years = patient_data.get("age_years", 0)
        age_months = patient_data.get("age_months", 0)
        
        # Определяем срочность на основе красных флагов и температуры
        urgency = UrgencyLevel.ROUTINE
        activated_specialists = ["INFECTION"]  # По умолчанию
        
        # Критические красные флаги -> EMERGENCY
        critical_flags = ["нарушение сознания", "судороги", "дыхательная недостаточность", "геморрагическая сыпь"]
        if any(flag.lower() in " ".join(red_flags).lower() for flag in critical_flags):
            urgency = UrgencyLevel.EMERGENCY
            activated_specialists = ["INFECTION", "IMMUNE"]
        # Высокая температура у маленьких детей -> URGENT
        elif (temperature >= 39.0 and (age_years < 3 or age_months < 36)) or temperature >= 40.0:
            urgency = UrgencyLevel.URGENT
            activated_specialists = ["INFECTION"]
        # Есть красные флаги -> URGENT
        elif red_flags:
            urgency = UrgencyLevel.URGENT
        
        logger.info(f"Fallback triage: urgency={urgency.value}, specialists={activated_specialists}")
        
        return {
            "urgency_level": urgency,
            "activated_specialists": activated_specialists,
            "reasoning": "Fallback triage based on basic patient data"
        }
    
    def _get_fallback_intake_data(self, user_input: str, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """Получение базовых данных из сообщения пользователя при ошибке агента (fallback)
        
        Args:
            user_input: Текст сообщения пользователя
            current_data: Текущие данные пациента
            
        Returns:
            Базовые данные пациента, извлеченные простым парсингом
        """
        import re
        
        fallback_data = current_data.copy() if current_data else {}
        
        # Простой парсинг возраста
        age_match = re.search(r'(\d+)\s*(год|лет|месяц|месяцев)', user_input.lower())
        if age_match:
            age_value = int(age_match.group(1))
            if 'месяц' in age_match.group(2):
                fallback_data["age_months"] = age_value
            else:
                fallback_data["age_years"] = age_value
        
        # Простой парсинг температуры
        temp_match = re.search(r'(\d+[.,]\d+|\d+)\s*°?c', user_input.lower())
        if temp_match:
            temp_value = float(temp_match.group(1).replace(',', '.'))
            fallback_data["temperature_current"] = temp_value
        
        # Простой парсинг длительности
        duration_match = re.search(r'(\d+)\s*(день|дня|дней)', user_input.lower())
        if duration_match:
            fallback_data["duration_days"] = int(duration_match.group(1))
        
        # Базовые симптомы (простой поиск ключевых слов)
        common_symptoms = ["кашель", "насморк", "боль", "рвота", "диарея", "сыпь"]
        found_symptoms = [s for s in common_symptoms if s in user_input.lower()]
        if found_symptoms:
            fallback_data["symptoms"] = found_symptoms
        
        logger.info(f"Fallback intake data extracted: {list(fallback_data.keys())}")
        return fallback_data
    
    def _update_patient_data_from_intake(
        self, 
        current_data: Dict[str, Any], 
        intake_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Обновление данных пациента из результата INTAKE агента"""
        
        updated = current_data.copy()
        
        # Обновление возраста
        if "patient_age" in intake_result:
            age_data = intake_result["patient_age"]
            updated["age_years"] = age_data.get("years")
            updated["age_months"] = age_data.get("months")
        
        # Обновление температуры
        if "temperature" in intake_result:
            temp_data = intake_result["temperature"]
            updated["temperature_current"] = temp_data.get("current")
            updated["temperature_max"] = temp_data.get("max")
            updated["temperature_pattern"] = temp_data.get("pattern")
        
        # Обновление длительности
        if "duration_days" in intake_result:
            updated["duration_days"] = intake_result["duration_days"]
        
        # Обновление симптомов
        if "symptoms" in intake_result:
            updated["symptoms"] = intake_result["symptoms"]
        
        # Обновление красных флагов
        if "red_flags" in intake_result:
            updated["red_flags"] = intake_result["red_flags"]
        
        # Обновление отсутствующей информации
        if "missing_critical_info" in intake_result:
            updated["missing_info"] = intake_result["missing_critical_info"]
        
        # Лабораторные и прочие структурированные данные (врач может вставить ОАК, СРБ и т.д.)
        if "lab_results" in intake_result and isinstance(intake_result["lab_results"], dict):
            prev = updated.get("lab_results") or {}
            if isinstance(prev, dict):
                merged = {**prev, **intake_result["lab_results"]}
                updated["lab_results"] = merged
            else:
                updated["lab_results"] = intake_result["lab_results"]
        
        if "anamnesis" in intake_result and isinstance(intake_result["anamnesis"], dict):
            prev_a = updated.get("anamnesis") or {}
            if isinstance(prev_a, dict):
                updated["anamnesis"] = {**prev_a, **intake_result["anamnesis"]}
            else:
                updated["anamnesis"] = intake_result["anamnesis"]
        
        if "physical_exam" in intake_result and isinstance(intake_result["physical_exam"], dict):
            prev_p = updated.get("physical_exam") or {}
            if isinstance(prev_p, dict):
                updated["physical_exam"] = {**prev_p, **intake_result["physical_exam"]}
            else:
                updated["physical_exam"] = intake_result["physical_exam"]
        
        return updated
    
    async def process_message(
        self,
        session_id: str,
        message: str,
        doctor_id: Optional[str] = None,
        timeout: int = 300,  # 5 минут таймаут по умолчанию
        progress_callback: Optional[Callable[[str, str, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Обработка сообщения через граф. Если передан progress_callback, граф стримится по шагам и после каждого узла вызывается callback(agent_key, title_ru, description)."""
        
        logger.info("=== PROCESS_MESSAGE STARTED ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Doctor ID: {doctor_id}")
        logger.info(f"Message: {message}")
        
        if not self._initialized:
            logger.info("Graph not initialized, initializing now...")
            await self.initialize()
        
        try:
            logger.info(f"Starting process_message for session {session_id}")
            
            # Пытаемся загрузить существующее состояние из Redis
            existing_state = await self.redis_manager.load_session_state(session_id)
            
            if existing_state:
                logger.info(f"Loaded existing state for session {session_id}")
                # Используем существующее состояние
                current_state = existing_state
                # Добавляем новое сообщение пользователя
                current_state = add_message(current_state, "user", message)
                # Обновляем временную метку
                current_state = update_timestamp(current_state)
            else:
                logger.info(f"Creating new state for session {session_id}")
                # Создаем новое состояние
                current_state = create_initial_state(session_id, doctor_id)
                # Добавляем сообщение пользователя
                current_state = add_message(current_state, "user", message)
            
            logger.info(f"Current state keys: {list(current_state.keys())}")
            logger.debug(f"Session ID in state: {current_state.get('session_id')}")
            logger.debug(f"Messages count in state: {len(current_state.get('messages', []))}")
            
            # Запуск графа с обработкой ошибок и таймаутом
            try:
                logger.info("=== GRAPH EXECUTION STARTING ===")
                logger.info(f"State before graph execution: {current_state}")
                import asyncio

                if progress_callback:
                    logger.info("Using astream with progress_callback (streaming agent progress)")
                    # astream() возвращает async generator — wait_for принимает только coroutine/Future; оборачиваем цикл в корутину
                    result = None

                    async def _consume_astream():
                        nonlocal result
                        async for event in self.graph.astream(
                            current_state,
                            stream_mode=["updates", "values"],
                            config={"recursion_limit": settings.graph_recursion_limit},
                        ):
                            # #region agent log
                            _ev_type = type(event).__name__
                            _ev_len = len(event) if isinstance(event, (list, tuple)) else None
                            _is_2 = isinstance(event, (list, tuple)) and len(event) == 2
                            _is_3 = isinstance(event, (list, tuple)) and len(event) == 3
                            logger.info("astream event: type=%s len=%s is_2tuple=%s is_3tuple=%s", _ev_type, _ev_len, _is_2, _is_3)
                            mode, payload = None, None
                            if isinstance(event, (list, tuple)):
                                if len(event) == 3:
                                    # (namespace, mode, payload) — subgraphs / часть версий LangGraph
                                    _, mode, payload = event[0], event[1], event[2]
                                elif len(event) == 2:
                                    mode, payload = event[0], event[1]
                            mode_s = str(mode) if mode is not None else ""
                            if mode is not None and payload is not None:
                                if mode_s == "updates" and isinstance(payload, dict):
                                    for node_name in payload:
                                        title_ru, description = AGENT_PROGRESS_LABELS.get(
                                            node_name, (node_name, "Обработка.")
                                        )
                                        logger.info("progress_callback: node=%s", node_name)
                                        await progress_callback(node_name, title_ru, description)
                                elif mode_s == "values" and isinstance(payload, Mapping):
                                    result = dict(payload) if not isinstance(payload, dict) else payload
                                    logger.info("astream: result set from values, keys=%s", list(result.keys())[:12])
                            elif isinstance(event, dict):
                                # stream_mode="values" (один режим) отдаёт целый state как dict
                                result = event

                    try:
                        await asyncio.wait_for(_consume_astream(), timeout=timeout)
                    except asyncio.TimeoutError:
                        logger.error(f"Graph execution timeout after {timeout} seconds")
                        return {
                            "success": False,
                            "error": f"Timeout: обработка заняла более {timeout} секунд",
                            "response": "Обработка сообщения заняла слишком много времени. Попробуйте еще раз.",
                            "session_id": session_id,
                        }
                    if result is None:
                        logger.error("Graph astream did not yield final state")
                        return {
                            "success": False,
                            "error": "Граф не вернул итоговое состояние.",
                            "response": "Произошла ошибка при обработке. Попробуйте еще раз.",
                            "session_id": session_id,
                        }
                else:
                    logger.info("Using ainvoke (no progress_callback)")
                    try:
                        result = await asyncio.wait_for(
                            self.graph.ainvoke(
                                current_state,
                                {"recursion_limit": settings.graph_recursion_limit},
                            ),
                            timeout=timeout,
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Graph execution timeout after {timeout} seconds")
                        return {
                            "success": False,
                            "error": f"Timeout: обработка заняла более {timeout} секунд",
                            "response": "Обработка сообщения заняла слишком много времени. Попробуйте еще раз.",
                            "session_id": session_id,
                        }

                logger.info("=== GRAPH EXECUTION COMPLETED ===")
                logger.info(f"Graph execution completed for session {session_id}")
                logger.info(f"Final state type: {type(result)}")
                logger.info(f"Final state keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                
                # Сохраняем состояние в Redis
                if isinstance(result, dict):
                    await self.redis_manager.save_session_state(session_id, result)
                    logger.info(f"State saved to Redis for session {session_id}")
                
                # Логируем ключевые поля результата
                if isinstance(result, dict):
                    logger.info(f"Final current_step: {result.get('current_step')}")
                    logger.info(f"Final urgency_level: {result.get('urgency_level')}")
                    logger.info(f"Final activated_specialists: {result.get('activated_specialists')}")
                    logger.info(f"Final messages count: {len(result.get('messages', []))}")
                    logger.info(f"Final needs_more_info: {result.get('needs_more_info')}")
                    logger.info(f"Final questions_to_ask: {result.get('questions_to_ask')}")
                    
                    # Логируем последнее сообщение для отладки
                    messages = result.get('messages', [])
                    if messages:
                        last_message = messages[-1]
                        logger.info(f"Last message type: {type(last_message)}")
                        if isinstance(last_message, dict):
                            logger.info(f"Last message content: {last_message.get('content', '')[:200]}...")
                        else:
                            logger.info(f"Last message: {str(last_message)[:200]}...")
                    
            except Exception as graph_error:
                logger.error("=== GRAPH EXECUTION FAILED ===")
                logger.error(f"Graph execution error: {str(graph_error)}")
                logger.error(f"Graph error type: {type(graph_error)}")
                import traceback
                logger.error(f"Graph traceback: {traceback.format_exc()}")
                
                # Возвращаем базовый ответ при ошибке графа
                return {
                    "success": False,
                    "error": f"Graph execution error: {str(graph_error)}",
                    "response": "Произошла ошибка при выполнении анализа. Пожалуйста, попробуйте еще раз.",
                    "session_id": session_id
                }
            
            # Проверяем результат
            if not isinstance(result, dict):
                logger.error(f"Invalid result type: {type(result)}")
                return {
                    "success": False,
                    "error": f"Invalid result type: {type(result)}",
                    "response": "Произошла ошибка при обработке результата.",
                    "session_id": session_id
                }
            
            # Формируем ответ
            response_data = {
                "success": True,
                "session_id": session_id,
                "state": result,
                "current_step": result.get("current_step"),
                "urgency_level": result.get("urgency_level"),
                "needs_more_info": result.get("needs_more_info", False),
                "questions_to_ask": result.get("questions_to_ask", []),
            }
            
            # Добавляем только последнее сообщение от ассистента
            if result.get("messages") and len(result["messages"]) > 0:
                # Ищем последнее сообщение от ассистента
                last_assistant_message = None
                for message in reversed(result["messages"]):
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        raw = message.get("content", "")
                        last_assistant_message = (raw if isinstance(raw, str) else str(raw or "")).strip()
                        break
                
                if last_assistant_message:
                    response_data["response"] = last_assistant_message
                    # При шаге feedback_requested в чате показываем сначала текст рекомендаций, затем блок обратной связи
                    if result.get("current_step") == "feedback_requested":
                        rec_text = (result.get("recommendations_text") or "").strip()
                        if not rec_text and result.get("synthesis_output") and isinstance(result["synthesis_output"], dict):
                            out = result["synthesis_output"].get("output")
                            rec_text = (out.get("recommendations_text") if isinstance(out, dict) else "") or ""
                            rec_text = (rec_text or "").strip()
                        if rec_text:
                            primary = result.get("primary_specialist")
                            header = ""
                            if primary and isinstance(primary, dict):
                                name = primary.get("name") or "Специалист"
                                timeframe = primary.get("timeframe") or ""
                                purpose = primary.get("purpose") or ""
                                header = f"📋 **Рекомендуемое направление: {name}**"
                                if timeframe:
                                    header += f"\n⏱ Сроки: {timeframe}"
                                if purpose:
                                    header += f"\n🎯 Цель: {purpose}"
                                header += "\n\n"
                            response_data["response"] = header + rec_text + "\n\n" + last_assistant_message
                            logger.info("Response includes recommendation text before feedback block")
                    logger.info(f"Response from last assistant message: {response_data['response'][:100]}...")
                else:
                    # Если нет сообщений от ассистента
                    response_data["response"] = "Анализ завершен."
            else:
                response_data["response"] = "Анализ завершен, но ответ не получен."
                logger.warning("No messages found in result")
            
            # Добавляем рекомендации если есть
            if result.get("synthesis_output"):
                response_data["recommendations"] = {
                    "primary_specialist": result.get("primary_specialist"),
                    "additional_specialists": result.get("additional_specialists", []),
                    "required_tests": result.get("required_tests", []),
                    "red_flags": result.get("red_flags", []),
                    "recommendations_text": result.get("recommendations_text")
                }
                # Добавляем возможные диагнозы если есть
                if result.get("possible_diagnoses"):
                    response_data["recommendations"]["possible_diagnoses"] = result.get("possible_diagnoses")
                    logger.info(f"Added {len(result.get('possible_diagnoses', []))} possible diagnoses to response")
                logger.info("Added recommendations to response")
            
            # Логика работы агентов: цепочка шагов с кратким описанием решений
            response_data["agent_workflow"] = self._build_agent_workflow(result)
            # Ссылки на клинические рекомендации, на которых основывается система
            response_data["clinical_sources"] = self._get_clinical_sources(result)
            
            # Не отдаём пустой/пробельный текст — иначе фронт не показывает сообщение
            resp_txt = (response_data.get("response") or "").strip()
            if not resp_txt:
                response_data["response"] = (
                    "По этому запросу не удалось сформулировать развёрнутый ответ. "
                    "Уточните клиническую картину или переформулируйте вопрос; смотрите также цепочку шагов агентов и рекомендации."
                )
                logger.warning("response was empty after strip; using fallback text for session %s", session_id)
            else:
                response_data["response"] = resp_txt

            logger.info("=== PROCESS_MESSAGE COMPLETED SUCCESSFULLY ===")
            logger.info(f"Response data keys: {list(response_data.keys())}")
            logger.info(f"Response success: {response_data['success']}")
            logger.info(f"Response length: {len(response_data.get('response', ''))}")
            
            return response_data
            
        except Exception as e:
            logger.error("=== PROCESS_MESSAGE FAILED ===")
            import traceback
            logger.error(f"Error processing message: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Session ID: {session_id}")
            logger.error(f"Message: {message}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Дополнительная диагностика
            if hasattr(e, '__cause__') and e.__cause__:
                logger.error(f"Cause: {e.__cause__}")
                logger.error(f"Cause type: {type(e.__cause__)}")
            
            return {
                "success": False,
                "error": str(e),
                "response": "Произошла ошибка при обработке сообщения. Попробуйте еще раз.",
                "session_id": session_id
            }
    
    def _build_agent_workflow(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Собирает цепочку шагов агентов с кратким описанием решений для отображения пользователю."""
        order = [
            ("intake_output", "intake", "Приём данных", "Сбор жалоб, возраста, температуры и симптомов пациента."),
            ("data_completeness_checker_output", "data_completeness_checker", "Проверка полноты данных", "Оценка достаточности данных для первичного заключения."),
            ("triage_output", "triage", "Триаж", "Определение срочности и активация направлений диагностики."),
            ("hypothesis_generator_output", "hypothesis_generator", "Гипотезы", "Формирование дифференциальных диагнозов."),
            ("question_output", "question", "Уточняющие вопросы", "Генерация вопросов для повышения уверенности."),
            ("infection_output", "infection", "Инфекционист", "Оценка инфекционных причин лихорадки."),
            ("immune_output", "immune", "Иммунолог", "Оценка иммунологических причин."),
            ("oncology_output", "oncology", "Онколог", "Оценка онкологических рисков."),
            ("rare_disease_output", "rare_disease", "Редкие заболевания", "Учёт редких причин лихорадки."),
            ("synthesis_output", "synthesis", "Синтез", "Финальное заключение и маршрутизация к специалисту."),
        ]
        workflow = []
        for key, agent_key, title_ru, default_reasoning in order:
            out = result.get(key)
            if not out or not isinstance(out, dict):
                continue
            agent_name = out.get("agent_name") or agent_key
            output = out.get("output") or {}
            reasoning = (
                output.get("reasoning")
                or output.get("data_quality_assessment")
                or output.get("summary")
                or output.get("recommended_next_steps")
            )
            if isinstance(reasoning, list):
                reasoning = "; ".join(str(x) for x in reasoning[:3])
            if not reasoning and output:
                reasoning = str(output.get("urgency_level") or output.get("most_likely") or list(output.keys())[:2])
            workflow.append({
                "step": len(workflow) + 1,
                "agent_key": agent_key,
                "title": title_ru,
                "role": default_reasoning,
                "reasoning": (reasoning or default_reasoning)[:500],
                "confidence": out.get("confidence"),
                "execution_time_ms": out.get("execution_time_ms"),
            })
        return workflow
    
    def _get_clinical_sources(self, result: Dict[str, Any]) -> List[Dict[str, str]]:
        """Возвращает ссылки на клинические рекомендации, на которых основывается система.

        Приоритет отображения: КР МЗ РФ (cr.minzdrav.gov.ru) выше прочих. Собирает sources
        из всех релевантных выходов агентов; дедуплицирует по url+раздел+цитата+утверждение.
        """
        collected: List[Dict[str, str]] = []
        seen_keys: set = set()

        def _add_items_from_output(agent_block: Any) -> None:
            if not isinstance(agent_block, dict):
                return
            out = agent_block.get("output") or {}
            if not isinstance(out, dict):
                return
            raw_sources = out.get("sources")
            if not isinstance(raw_sources, list):
                return
            for s in raw_sources:
                if not isinstance(s, dict):
                    continue
                norm = _normalize_source_dict(s)
                if not norm:
                    continue
                dk = _source_dedup_key(norm)
                if dk in seen_keys:
                    continue
                seen_keys.add(dk)
                collected.append(norm)

        # Сначала ответы моделей (порядок ключей — от ранних шагов к синтезу)
        for key in _CLINICAL_SOURCE_STATE_KEYS:
            _add_items_from_output(result.get(key))

        # Базовые рекомендации (если ещё не встречались)
        baseline = [
            {
                "title": "Клинические рекомендации «Лихорадка у детей» (Минздрав РФ, 2021)",
                "url": "https://cr.minzdrav.gov.ru/recomend/679_1",
                "description": "Диагностика и лечение лихорадки неясного генеза у детей.",
            },
            {
                "title": "NICE Guideline: Fever in under 5s (2019)",
                "url": "https://www.nice.org.uk/guidance/ng143",
                "description": "Assessment and initial management of feverish illness in children.",
            },
            {
                "title": "IDSA: Clinical Practice Guideline for the Management of Fever (2013)",
                "url": "https://www.idsociety.org/practice-guideline/fever-and-fever-of-unknown-origin/",
                "description": "Evidence-based approach to fever and FUO.",
            },
        ]
        for b in baseline:
            norm = _normalize_source_dict(b)
            if not norm:
                continue
            dk = _source_dedup_key(norm)
            if dk in seen_keys:
                continue
            seen_keys.add(dk)
            collected.append(norm)

        # Сортировка: КР МЗ РФ первыми, остальные — в исходном порядке сбора
        minzdrav = [x for x in collected if _is_minzdrav_cr_url(x.get("url", ""))]
        other = [x for x in collected if not _is_minzdrav_cr_url(x.get("url", ""))]
        ordered = minzdrav + other
        return ordered[:15]
    
    async def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получение текущего состояния сессии из Redis"""
        
        if not self._initialized:
            await self.initialize()
        
        try:
            # Загружаем состояние из Redis
            state = await self.redis_manager.load_session_state(session_id)
            
            if state:
                logger.info(f"Session {session_id} loaded from Redis")
                return state
            else:
                logger.info(f"Session {session_id} not found in Redis")
                return None
            
        except Exception as e:
            logger.error(f"Error getting session state: {str(e)}")
            return None
    
    async def create_session(self, session_id: str, doctor_id: Optional[str] = None) -> GraphState:
        """Создание новой сессии и сохранение в Redis"""
        
        if not self._initialized:
            await self.initialize()
        
        # Создание начального состояния
        initial_state = create_initial_state(session_id, doctor_id)
        
        # Сохраняем состояние в Redis
        await self.redis_manager.save_session_state(session_id, initial_state)
        logger.info(f"New session {session_id} created and saved to Redis")
        
        return initial_state


# Глобальный экземпляр графа
_graph_instance: Optional[FeverRoutingGraph] = None


async def get_fever_routing_graph() -> FeverRoutingGraph:
    """Получение экземпляра графа"""
    global _graph_instance
    
    if _graph_instance is None:
        _graph_instance = FeverRoutingGraph()
        await _graph_instance.initialize()
    
    return _graph_instance