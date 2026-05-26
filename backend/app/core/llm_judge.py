"""
LLM-as-a-Judge: оценка качества выходов агентов через LLM-судью.
Контракт: (input_text, agent_output, agent_name, criterion) -> (score, reason).
Поддержка метрик: Answer Relevancy, Format correctness, Helpfulness (G-Eval-подобные).
"""

import re
import logging
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Критерии оценки (метрики)
CRITERION_ANSWER_RELEVANCY = "answer_relevancy"
CRITERION_FORMAT_CORRECTNESS = "format_correctness"
CRITERION_HELPFULNESS = "helpfulness"
CRITERION_CLINICAL_APPROPRIATENESS = "clinical_appropriateness"
CRITERION_URGENCY_ACCURACY = "urgency_accuracy"
CRITERION_SPECIALIST_ROUTING = "specialist_routing"

CRITERIA_PROMPTS = {
    CRITERION_ANSWER_RELEVANCY: (
        "Оцени, насколько ответ агента релевантен исходному запросу и контексту. "
        "Учитывай: отвечает ли на вопрос, не уходит ли от темы, покрывает ли ключевые аспекты."
    ),
    CRITERION_FORMAT_CORRECTNESS: (
        "Оцени, соблюдён ли требуемый формат вывода (например JSON с нужными полями, структура). "
        "Учитывай наличие обязательных полей и типы данных."
    ),
    CRITERION_HELPFULNESS: (
        "Оцени, насколько ответ полезен и полон для пользователя. "
        "Учитывай: практическую применимость, полноту рекомендаций, ясность."
    ),
    CRITERION_CLINICAL_APPROPRIATENESS: (
        "Оцени клиническую обоснованность и полноту рекомендаций по шкале 1–5. "
        "Учитывай соответствие стандартам, отсутствие опасных советов, полноту обоснования."
    ),
    CRITERION_URGENCY_ACCURACY: (
        "Оцени, насколько точно определён уровень срочности (emergency/urgent/routine) "
        "в ответе агента относительно описанной клинической картины. "
        "Шкала оценки: "
        "5 — уровень срочности полностью соответствует клинике (например, экстренный при признаках сепсиса или менингококкемии, плановый при лёгком ОРВИ); "
        "4 — уровень срочности правильный, но обоснование неполное или не отражает все красные флаги; "
        "3 — срочность завышена или занижена на один уровень (например, urgent вместо emergency при тяжёлом состоянии); "
        "2 — срочность существенно неверна (например, routine при признаках шока или длительной лихорадке с В-симптомами); "
        "1 — опасная ошибка срочности, способная причинить непосредственный вред пациенту (например, routine при сепсисе или нейтропеническом лихорадочном синдроме). "
        "Опирайся на клинические рекомендации МЗ РФ и международные педиатрические протоколы триажа."
    ),
    CRITERION_SPECIALIST_ROUTING: (
        "Оцени, насколько клинически обоснован выбор специалистов (primary_specialist и additional_specialists) "
        "в ответе агента для данной клинической ситуации. "
        "Шкала оценки: "
        "5 — все рекомендованные специалисты клинически оправданы, ни один необходимый специалист не пропущен; "
        "4 — основной специалист верен, есть незначительный пропуск дополнительного, не влияющий на безопасность; "
        "3 — основной специалист верен, но пропущен один клинически важный дополнительный специалист (например, нет нефролога при подозрении на СКВ); "
        "2 — неверный основной специалист или опасный пропуск (например, нет онколога/гематолога при В-симптомах, нет ОРИТ при шоке); "
        "1 — маршрутизация полностью неверна или опасно задержит необходимую специализированную помощь. "
        "Учитывай педиатрический контекст и специфику каждого клинического сценария."
    ),
}


@dataclass
class JudgeResult:
    """Результат оценки LLM-судьи."""
    score: float
    reason: str
    criterion: str
    binary_verdict: Optional[bool] = None  # для бинарной оценки 0/1


def _build_judge_prompt(
    input_text: str,
    agent_output: str,
    agent_name: str,
    criterion: str,
    use_cot: bool = True,
) -> str:
    """Формирует промпт для судьи с опциональным CoT."""
    criterion_desc = CRITERIA_PROMPTS.get(
        criterion,
        "Оцени качество ответа по заданному контексту."
    )
    cot_instruction = ""
    if use_cot:
        cot_instruction = (
            "\nСначала кратко опиши шаги рассуждения (1–2 предложения), "
            "затем выведи оценку в формате: ОЦЕНКА: <число от 1 до 5> ОБОСНОВАНИЕ: <текст>"
        )
    return (
        f"Ты — эксперт-оценщик качества ответов ИИ. Критерий: {criterion_desc}.{cot_instruction}\n\n"
        f"Агент: {agent_name}\n"
        f"Вход (запрос/контекст):\n{input_text[:2000]}\n\n"
        f"Ответ агента:\n{agent_output[:3000]}\n\n"
        "Выведи оценку от 1 до 5 (1 — плохо, 5 — отлично) и краткое обоснование."
    )


def parse_judge_response(raw_text: str) -> Tuple[float, str]:
    """
    Парсит ответ LLM-судьи: извлекает score (1–5) и reason.
    Returns:
        (score, reason). Если парсинг не удался, score=0.0, reason=raw_text.
    """
    if not raw_text or not raw_text.strip():
        return 0.0, "Пустой ответ судьи"
    text = raw_text.strip()
    score = 0.0
    reason = text

    # Паттерны: "ОЦЕНКА: 4" / "Score: 4" / "оценка 4" / число 1-5 в начале строки
    patterns = [
        r"[Оо]ценка?\s*[:\s]+\s*(\d)",
        r"score\s*[:\s]+\s*(\d)",
        r"\b([1-5])\s*/\s*5",
        r"^([1-5])\s*[\.\)]\s",
        r"(\d)\s*балл",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            try:
                s = float(m.group(1))
                if 1 <= s <= 5:
                    score = s
                    break
            except (ValueError, IndexError):
                pass

    # Обоснование: после "ОБОСНОВАНИЕ:" или "reason:" или берём всё после первого числа
    reason_m = re.search(
        r"(?:обоснование|reason|пояснение)\s*[:\s]+(.+)$",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if reason_m:
        reason = reason_m.group(1).strip()[:500]
    elif score > 0:
        # Убираем из reason строку с оценкой
        reason = re.sub(r"оценка\s*[:\s]*\d", "", text, flags=re.IGNORECASE).strip()[:500]

    return score, reason or text[:500]


async def evaluate_with_llm_judge(
    input_text: str,
    agent_output: str,
    agent_name: str,
    criterion: str,
    use_cot: bool = True,
) -> JudgeResult:
    """
    Вызывает LLM-судью для оценки пары (input, output).
    Использует тот же Yandex AI Studio клиент с отдельным judge-промптом.
    """
    try:
        from app.core.ai_studio import get_ai_studio_client
        client = await get_ai_studio_client()
    except Exception as e:
        logger.warning(f"LLM Judge: could not get AI client: {e}")
        return JudgeResult(score=0.0, reason=f"Judge unavailable: {e}", criterion=criterion)

    prompt = _build_judge_prompt(input_text, agent_output, agent_name, criterion, use_cot=use_cot)
    system_prompt = (
        "Ты — объективный оценщик качества ответов ИИ. Отвечай только оценкой и обоснованием по инструкции."
    )
    try:
        # Вызов без кэша (оценки не кэшируем по умолчанию)
        agent_config = client.openai_client  # используем тот же модель-конфиг через call
        # Используем первый доступный агент для модели (например intake)
        from app.config import settings
        agent_config_dict = settings.get_agent_config("intake")
        model_uri = agent_config_dict.get("model_uri", "gpt-4")
        response = client.openai_client.chat.completions.create(
            model=model_uri,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        text = (response.choices[0].message.content or "").strip()
        score, reason = parse_judge_response(text)
        binary = None
        if criterion == CRITERION_FORMAT_CORRECTNESS:
            binary = score >= 4.0
        return JudgeResult(score=score, reason=reason, criterion=criterion, binary_verdict=binary)
    except Exception as e:
        logger.exception(f"LLM Judge call failed: {e}")
        return JudgeResult(score=0.0, reason=str(e), criterion=criterion)


def evaluate_parsing_only(raw_text: str, criterion: str = "test") -> JudgeResult:
    """Только парсинг ответа судьи (для юнит-тестов без вызова API)."""
    score, reason = parse_judge_response(raw_text)
    return JudgeResult(score=score, reason=reason, criterion=criterion)
