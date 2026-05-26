#!/usr/bin/env python3
"""
Прогон виртуальных кейсов из tests/fixtures/eval_cases.json через LangGraph.

По умолчанию RUN_MODE=instant (один запрос доходит до synthesis после triage).
Запуск из каталога backend с доступом к Redis/Postgres (как у основного приложения):

  cd backend && RUN_MODE=instant python scripts/run_virtual_cases.py
  RUN_MODE=instant python scripts/run_virtual_cases.py --limit 2

В Docker на ВМ:

  docker compose exec -T backend python scripts/run_virtual_cases.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# До импорта приложения — режим маршрутизации
if "RUN_MODE" not in os.environ:
    os.environ["RUN_MODE"] = "instant"

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "eval_cases.json"
ARTIFACTS = BACKEND_ROOT / "tests" / "artifacts"


def _urgency_str(val) -> str:
    if val is None:
        return ""
    if hasattr(val, "value"):
        return str(val.value).lower().strip()
    return str(val).lower().strip()


async def run_one(graph, case: dict, timeout: int) -> dict:
    case_id = case.get("id", "unknown")
    session_id = str(uuid.uuid4())
    await graph.create_session(session_id, "virtual_case_runner")
    # Иначе при первом сообщении _after_data_check уходит в «question» (фаза gathering_info),
    # триаж не выполняется — для эталонов срочности нужна фаза диагностики.
    st = await graph.redis_manager.load_session_state(session_id)
    if st:
        st["dialogue_phase"] = "diagnosis"
        st["data_completeness_score"] = max(st.get("data_completeness_score") or 0, 85)
        await graph.redis_manager.save_session_state(session_id, st)

    resp = await graph.process_message(
        session_id=session_id,
        message=case.get("input_text", ""),
        doctor_id="virtual_case_runner",
        timeout=timeout,
    )
    state = resp.get("state") or {}
    triage_out = (state.get("triage_output") or {}).get("output") or {}
    triage_u = _urgency_str(triage_out.get("urgency_level"))
    # process_message кладёт urgency_level на верхний уровень ответа
    top_u = _urgency_str(resp.get("urgency_level"))
    state_u = _urgency_str(state.get("urgency_level"))
    urgency = top_u or state_u or triage_u
    expected = _urgency_str(case.get("expected_urgency"))
    if urgency and expected:
        matched = expected == urgency or expected in urgency or urgency in expected
    else:
        matched = False

    syn = state.get("synthesis_output") or {}
    syn_out = syn.get("output") if isinstance(syn, dict) else None
    sources_n = 0
    if isinstance(syn_out, dict) and syn_out.get("sources"):
        sources_n = len(syn_out["sources"])

    return {
        "case_id": case_id,
        "success": resp.get("success"),
        "current_step": resp.get("current_step"),
        "urgency_top_level": top_u,
        "urgency_from_triage_json": triage_u,
        "urgency_from_state": state_u,
        "resolved_urgency": urgency,
        "expected_urgency": expected,
        "expected_match": matched,
        "synthesis_sources_count": sources_n,
        "error": resp.get("error"),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run virtual cases through FeverRoutingGraph")
    parser.add_argument("--limit", type=int, default=None, help="Max number of cases")
    parser.add_argument("--timeout", type=int, default=420, help="Per-case graph timeout (seconds)")
    parser.add_argument("--out", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    if not FIXTURES.is_file():
        print(f"Fixture not found: {FIXTURES}", file=sys.stderr)
        return 1

    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]

    from app.core.langgraph_app import get_fever_routing_graph

    graph = await get_fever_routing_graph()
    results = []
    for case in cases:
        cid = case.get("id", "?")
        print(f"\n--- {cid} ---", flush=True)
        try:
            row = await run_one(graph, case, timeout=args.timeout)
        except Exception as e:
            row = {
                "case_id": cid,
                "success": False,
                "error": str(e),
                "expected_match": False,
            }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False, indent=2), flush=True)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out_path = args.out or ARTIFACTS / f"virtual_cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "run_mode": os.environ.get("RUN_MODE", ""),
        "fixture": str(FIXTURES),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nОтчёт: {out_path}", flush=True)

    ok = sum(1 for r in results if r.get("expected_match"))
    success = sum(1 for r in results if r.get("success"))
    print(f"Итого: успех графа {success}/{len(results)}, совпадение срочности с эталоном {ok}/{len(results)}", flush=True)
    return 0 if success == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
