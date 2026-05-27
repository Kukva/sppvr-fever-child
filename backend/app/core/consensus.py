"""Консенсусный механизм: взвешенное голосование специалистов по уровню срочности."""

from typing import Any, Dict, List, Optional, Tuple

URGENCY_RANK = {"emergency": 2, "urgent": 1, "routine": 0}
RANK_TO_URGENCY = {2: "emergency", 1: "urgent", 0: "routine"}

SPECIALIST_KEYS = ["infection", "immune", "oncology", "rare_disease"]


def _extract_vote(agent_output: Optional[Dict[str, Any]]) -> Optional[Tuple[str, float]]:
    """Извлекает (urgency, confidence) из AgentOutput специалиста."""
    if not agent_output:
        return None
    output = agent_output.get("output") or {}
    urgency_raw = str(output.get("recommended_urgency", "")).lower().strip()
    if urgency_raw not in URGENCY_RANK:
        return None
    confidence = float(output.get("confidence") or agent_output.get("confidence") or 0.5)
    confidence = max(0.0, min(1.0, confidence))
    return urgency_raw, confidence


def calculate_weighted_consensus(state: Dict[str, Any]) -> Dict[str, Any]:
    """Взвешенное голосование специалистов по urgency_level.

    Возвращает dict с полями:
      - consensus_urgency: str  итоговый уровень (emergency/urgent/routine)
      - votes: dict             {urgency: суммарный вес}
      - participating: list     имена проголосовавших специалистов
      - conflict: bool          True если голоса расходятся более чем на 1 уровень
      - conflict_agents: list   пары конфликтующих специалистов
    """
    votes: Dict[str, float] = {"emergency": 0.0, "urgent": 0.0, "routine": 0.0}
    participating: List[str] = []
    urgency_per_agent: Dict[str, str] = {}

    for name in SPECIALIST_KEYS:
        agent_output = state.get(f"{name}_output")
        result = _extract_vote(agent_output)
        if result is None:
            continue
        urgency, confidence = result
        votes[urgency] += confidence
        participating.append(name)
        urgency_per_agent[name] = urgency

    if not participating:
        triage_urgency = _get_triage_urgency(state)
        return {
            "consensus_urgency": triage_urgency,
            "votes": votes,
            "participating": [],
            "conflict": False,
            "conflict_agents": [],
        }

    # Итоговый уровень — тот, у которого наибольший суммарный вес
    consensus_urgency = max(votes, key=lambda u: votes[u])

    # Конфликт: есть ли специалисты с расхождением > 1 уровня
    conflict_agents: List[str] = []
    agents = list(urgency_per_agent.items())
    for i in range(len(agents)):
        for j in range(i + 1, len(agents)):
            a_name, a_urg = agents[i]
            b_name, b_urg = agents[j]
            if abs(URGENCY_RANK[a_urg] - URGENCY_RANK[b_urg]) > 1:
                conflict_agents.append(f"{a_name}({a_urg}) vs {b_name}({b_urg})")

    # Безопасность: если triage говорит emergency — консенсус не понижает
    triage_urgency = _get_triage_urgency(state)
    if triage_urgency == "emergency" and consensus_urgency != "emergency":
        consensus_urgency = "emergency"

    return {
        "consensus_urgency": consensus_urgency,
        "votes": {k: round(v, 3) for k, v in votes.items()},
        "participating": participating,
        "conflict": len(conflict_agents) > 0,
        "conflict_agents": conflict_agents,
    }


def _get_triage_urgency(state: Dict[str, Any]) -> str:
    urgency = state.get("urgency_level")
    if urgency is None:
        return "routine"
    if hasattr(urgency, "value"):
        return urgency.value.lower()
    return str(urgency).lower()
