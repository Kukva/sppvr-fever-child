#!/usr/bin/env python3
"""Прогон одного кейса с выводом шагов и консенсуса специалистов."""

import asyncio, json, sys, uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import os
os.chdir(BACKEND_ROOT)

CASE_ID = "case_017"  # 3 месяца, постпрививочная реакция АКДС — ожидается routine, специалист не нужен

CASES_FILE = BACKEND_ROOT / "tests" / "fixtures" / "eval_cases.json"
with open(CASES_FILE, encoding="utf-8") as f:
    cases = {c["id"]: c for c in json.load(f)}

case = cases[CASE_ID]
print(f"\n{'='*70}")
print(f"КЕЙС: {CASE_ID}")
print(f"Ожидаемая срочность: {case['expected_urgency']}")
print(f"Ожидаемый специалист: {case['expected_specialist']}")
print(f"\nВВОД:\n{case['input_text']}")
print(f"{'='*70}\n")


async def main():
    from app.core.langgraph_app import FeverRoutingGraph
    from app.core.consensus import calculate_weighted_consensus

    graph = FeverRoutingGraph()
    await graph.initialize()
    session_id = str(uuid.uuid4())

    benchmark_input = case["input_text"] + "\n\nДругих данных нет. Анализы, если не указаны выше, не проводились."

    print(">>> ХОД 1: первичный ввод...")
    result1 = await graph.process_message(session_id=session_id, message=benchmark_input)
    print(f"    current_step: {result1.get('current_step')}")
    print(f"    urgency_level: {result1.get('urgency_level')}")
    print(f"    needs_more_info: {result1.get('needs_more_info')}")

    _FINAL = {"synthesis_complete", "feedback_requested", "complete"}
    if result1.get("current_step") in _FINAL:
        state = result1.get("state", {})
    else:
        existing = await graph.redis_manager.load_session_state(session_id)
        if existing:
            existing["questions_asked_count"] = 20
            existing["dialogue_phase"] = "diagnosis"
            existing["needs_more_info"] = False
            if existing.get("data_completeness_score", 0) < 80:
                existing["data_completeness_score"] = 85
            await graph.redis_manager.save_session_state(session_id, existing)

        print("\n>>> ХОД 2: запрос итогового заключения...")
        result2 = await graph.process_message(
            session_id=session_id,
            message="Данных достаточно. Дайте итоговое клиническое заключение.",
        )
        print(f"    current_step: {result2.get('current_step')}")
        print(f"    urgency_level: {result2.get('urgency_level')}")
        state = result2.get("state", {})

    # Финальное состояние из Redis
    final_state = await graph.redis_manager.load_session_state(session_id) or state

    print(f"\n{'─'*70}")
    pd = final_state.get("patient_data", {})
    print("PATIENT_DATA (возраст):")
    print(f"  age_years:  {pd.get('age_years')}")
    print(f"  age_months: {pd.get('age_months')}")
    print(f"  age_weeks:  {pd.get('age_weeks')}")
    print(f"  temperature_current: {pd.get('temperature_current')}")
    print(f"  red_flags: {pd.get('red_flags', [])}")
    print(f"  anamnesis: {pd.get('anamnesis', {})}")
    print(f"\nАКТИВИРОВАННЫЕ СПЕЦИАЛИСТЫ:", final_state.get("activated_specialists", []))
    print(f"{'─'*70}")

    # Вывод по каждому специалисту
    for sp in ["infection", "immune", "oncology", "rare_disease"]:
        out = final_state.get(f"{sp}_output")
        if not out:
            continue
        content = out.get("output", {})
        conf = out.get("confidence", "?")
        rec_urg = content.get("recommended_urgency", "—")
        print(f"\n[{sp.upper()}]")
        print(f"  confidence:          {conf}")
        print(f"  recommended_urgency: {rec_urg}")
        if sp == "infection":
            print(f"  most_likely:         {content.get('most_likely', '—')}")
            excl = content.get("cannot_exclude", [])
            if excl:
                print(f"  cannot_exclude:      {excl[:3]}")
        elif sp == "immune":
            cond = content.get("relevant_conditions", [])
            print(f"  relevant_conditions: {cond[:3]}")
        elif sp == "oncology":
            print(f"  oncological_risk:    {content.get('oncological_risk', '—')}")
            flags = content.get("red_flags_present", [])
            print(f"  red_flags_present:   {flags[:3]}")
        elif sp == "rare_disease":
            dx = content.get("rare_diagnoses_to_consider", [])
            print(f"  rare_diagnoses:      {dx[:3]}")

    print(f"\n{'─'*70}")
    consensus = calculate_weighted_consensus(final_state)
    print("КОНСЕНСУС СПЕЦИАЛИСТОВ:")
    print(f"  consensus_urgency: {consensus['consensus_urgency']}")
    print(f"  votes:             {consensus['votes']}")
    print(f"  participating:     {consensus['participating']}")
    print(f"  conflict:          {consensus['conflict']}")
    if consensus["conflict_agents"]:
        print(f"  conflict_agents:   {consensus['conflict_agents']}")

    print(f"\n{'─'*70}")
    triage = final_state.get("triage_output") or {}
    triage_out = triage.get("output", {})
    print(f"ТРИАЖ:             urgency={final_state.get('urgency_level')}  confidence={triage.get('confidence','?')}")

    synthesis = final_state.get("synthesis_output") or {}
    synthesis_out = synthesis.get("output", {}) or {}
    print(f"\n{'─'*70}")
    print("СИНТЕЗ (финальный ответ):")
    response = result2.get("response") if "result2" in dir() else result1.get("response")
    if response:
        print(response[:1200])
    else:
        print("  [нет ответа]")

asyncio.run(main())
