"""Модуль для парсинга ответов пользователей на запрос обратной связи"""

import re
from typing import Dict, Any


def parse_feedback_response(user_input: str) -> Dict[str, Any]:
    """
    Парсит ответ пользователя на запрос обратной связи.
    
    Извлекает:
    - was_helpful: была ли рекомендация полезной
    - helped_decision: помогла ли принять решение
    - rating: рейтинг от 1 до 5 (если указан)
    - comment: дополнительный комментарий (если есть)
    
    Args:
        user_input: Текст ответа пользователя
        
    Returns:
        Словарь с полями: was_helpful, helped_decision, rating, comment
    """
    if not user_input:
        return {
            "was_helpful": False,
            "helped_decision": False,
            "rating": None,
            "comment": None
        }
    
    user_input_lower = user_input.lower()
    
    # Паттерны для определения полезности
    helpful_patterns_positive = ["да", "yes", "полезна", "помогла", "полезно", "была полезна", "помогла принять"]
    helpful_patterns_negative = ["нет", "no", "не полезна", "не полезно", "не была полезна"]
    
    # Паттерны для определения помощи в принятии решения
    decision_patterns_positive = ["да", "yes", "помогла", "решение", "принять", "помогла принять решение"]
    decision_patterns_negative = ["нет", "no", "не помогла", "не принять", "не помогла принять"]
    
    # Сначала проверяем явные отрицания (приоритет над позитивом)
    has_negative_helpful = any(pattern in user_input_lower for pattern in helpful_patterns_negative)
    has_negative_decision = any(pattern in user_input_lower for pattern in decision_patterns_negative)
    # Неоднозначные фразы без явного да/нет — трактуем как отрицательные
    ambiguous = any(phrase in user_input_lower for phrase in ["может быть", "не уверен", "не знаю", "затрудняюсь"])

    # Определяем was_helpful (отрицание имеет приоритет)
    was_helpful = False
    if has_negative_helpful or ambiguous:
        was_helpful = False
    elif any(pattern in user_input_lower for pattern in helpful_patterns_positive):
        was_helpful = True
    elif any(word in user_input_lower for word in ["спасибо", "thanks", "хорошо", "отлично", "благодарю"]):
        was_helpful = True

    # Определяем helped_decision (отрицание имеет приоритет)
    helped_decision = False
    if has_negative_decision or ambiguous:
        helped_decision = False
    elif any(pattern in user_input_lower for pattern in decision_patterns_positive):
        helped_decision = True
    elif was_helpful and not has_negative_decision:
        helped_decision = True
    
    # Извлекаем рейтинг если есть (1-5)
    rating = None
    rating_match = re.search(r'[1-5]', user_input)
    if rating_match:
        rating = int(rating_match.group())
    
    # Извлекаем комментарий (текст, который явно не часть шаблона да/нет)
    comment = None
    if len(user_input) > 30:  # Достаточно длинный ответ — возможен комментарий
        comment_text = user_input
        for pattern in helpful_patterns_positive + helpful_patterns_negative + decision_patterns_positive + decision_patterns_negative:
            comment_text = comment_text.replace(pattern, "")
        comment_text = re.sub(r"[,.]", " ", comment_text).strip()
        # Не считаем комментарием остаток шаблона вроде "Да была Да"
        if len(comment_text) > 20:
            comment = comment_text
    
    return {
        "was_helpful": was_helpful,
        "helped_decision": helped_decision,
        "rating": rating,
        "comment": comment
    }
