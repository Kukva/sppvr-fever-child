#!/usr/bin/env python3
"""
Скрипт бенчмарка оценки агентов: прогон кейсов из eval_cases.json,
вызов LLM-as-a-Judge по 6 метрикам (relevancy, format, helpfulness,
clinical_appropriateness, urgency_accuracy, specialist_routing).
Результаты сохраняются в backend/tests/artifacts/benchmark_YYYYMMDD_HHMMSS.json.

Запуск (из корня backend):
  python scripts/run_eval_benchmark.py
  python scripts/run_eval_benchmark.py --no-llm   # без вызова судьи
  python scripts/run_eval_benchmark.py --limit 3  # только 3 кейса
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

FIXTURES_DIR = BACKEND_ROOT / "tests" / "fixtures"
ARTIFACTS_DIR = BACKEND_ROOT / "tests" / "artifacts"
EVAL_CASES_FILE = FIXTURES_DIR / "eval_cases.json"

ALL_CRITERIA = [
    "answer_relevancy",
    "format_correctness",
    "helpfulness",
    "clinical_appropriateness",
    "urgency_accuracy",
    "specialist_routing",
]

PASS_THRESHOLD = 4.0


def load_eval_cases(limit=None):
    if not EVAL_CASES_FILE.exists():
        print(f"Fixtures file not found: {EVAL_CASES_FILE}")
        return []
    with open(EVAL_CASES_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)
    if limit:
        cases = cases[:limit]
    return cases


def _compute_summary(results):
    criterion_scores = {c: [] for c in ALL_CRITERIA}
    pass_counts = []
    for r in results:
        case_passes = []
        for c in ALL_CRITERIA:
            score = r["scores"].get(c)
            if score is not None and score > 0:
                criterion_scores[c].append(score)
                case_passes.append(score >= PASS_THRESHOLD)
        if case_passes:
            pass_counts.append(all(case_passes))

    mean_per_criterion = {}
    for c in ALL_CRITERIA:
        vals = criterion_scores[c]
        mean_per_criterion[c] = round(sum(vals) / len(vals), 2) if vals else None

    overall_pass_rate = round(sum(pass_counts) / len(pass_counts), 3) if pass_counts else 0.0
    return {"mean_per_criterion": mean_per_criterion, "overall_pass_rate": overall_pass_rate}


def print_results_table(results, summary):
    short_names = {
        "answer_relevancy":         "ans_rel",
        "format_correctness":       "fmt_ok",
        "helpfulness":              "help",
        "clinical_appropriateness": "clin",
        "urgency_accuracy":         "urg_acc",
        "specialist_routing":       "spec_rt",
    }
    col_id = 12
    col_urg = 10
    col_qual = 8
    col_crit = 9

    total_width = col_id + 1 + col_urg + 1 + col_qual + 1 + (col_crit + 2) * len(ALL_CRITERIA)
    sep = "-" * total_width
    header = (
        f"{'case_id':<{col_id}} "
        f"{'exp_urg':<{col_urg}} "
        f"{'quality':<{col_qual}} "
        + "  ".join(f"{short_names[c]:<{col_crit}}" for c in ALL_CRITERIA)
    )
    print("\n" + sep)
    print(header)
    print(sep)

    for r in results:
        quality = r.get("mock_quality", "-")
        cells = []
        for c in ALL_CRITERIA:
            score = r["scores"].get(c)
            pf = r.get("pass_fail", {}).get(c)
            if score is not None and score > 0:
                pf_str = "P" if pf else "F"
                cells.append(f"{score:.1f} {pf_str}")
            else:
                cells.append("--   ")
        row = (
            f"{r['case_id']:<{col_id}} "
            f"{(r.get('expected_urgency') or '-'):<{col_urg}} "
            f"{quality:<{col_qual}} "
            + "  ".join(f"{c:<{col_crit}}" for c in cells)
        )
        print(row)

    print(sep)
    means = summary.get("mean_per_criterion", {})
    mean_cells = []
    for c in ALL_CRITERIA:
        m = means.get(c)
        mean_cells.append(f"{m:.2f}   " if m is not None else "--     ")
    print(
        f"{'MEAN':<{col_id}} "
        f"{'':<{col_urg}} "
        f"{'':<{col_qual}} "
        + "  ".join(f"{c:<{col_crit}}" for c in mean_cells)
    )
    print(sep)
    overall = summary.get("overall_pass_rate", 0.0)
    print(f"\nOverall pass rate (all criteria >= {PASS_THRESHOLD}): {overall:.1%}\n")


async def get_live_output(input_text: str, run_mode: str = "instant") -> str:
    """Прогнать кейс через реальный граф и вернуть финальный ответ ассистента."""
    import uuid
    from app.core.langgraph_app import MedicalRoutingGraph
    from app.core.state import create_initial_state

    graph = MedicalRoutingGraph()
    session_id = str(uuid.uuid4())
    state = create_initial_state(session_id=session_id, run_mode=run_mode)

    result = await graph.process_message(
        session_id=session_id,
        message=input_text,
    )
    # Берём последнее сообщение ассистента из финального состояния
    messages = result.get("messages") or []
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_msgs:
        return "[no assistant output]"
    return assistant_msgs[-1].get("content", "[empty]")


async def run_benchmark(use_llm_judge=True, limit=None, live=False):
    cases = load_eval_cases(limit=limit)
    if not cases:
        return {"error": "No cases loaded", "results": [], "timestamp": datetime.now().isoformat()}

    results = []
    for case in cases:
        case_id = case.get("id", "unknown")
        input_text = case.get("input_text", "")

        # Live-режим: реальный граф; иначе mock_output
        if live:
            print(f"  [{case_id}] calling live graph...")
            try:
                agent_output = await get_live_output(input_text)
            except Exception as e:
                agent_output = f"[live error: {e}]"
                print(f"  [{case_id}] LIVE ERROR: {e}")
        else:
            agent_output = case.get("mock_output") or f"[Mock output for {case_id}]"

        record = {
            "case_id": case_id,
            "input_text": input_text[:200],
            "expected_urgency": case.get("expected_urgency"),
            "expected_specialist": case.get("expected_specialist"),
            "expected_reasoning": case.get("expected_reasoning", ""),
            "zero_tolerance": case.get("zero_tolerance", False),
            "mock_quality": case.get("mock_quality", "live" if live else "mock"),
            "live_output": agent_output if live else None,
            "scores": {},
            "reasons": {},
            "pass_fail": {},
        }
        if use_llm_judge and input_text and agent_output and not agent_output.startswith("["):
            try:
                from app.core.llm_judge import (
                    evaluate_with_llm_judge,
                    CRITERION_ANSWER_RELEVANCY,
                    CRITERION_FORMAT_CORRECTNESS,
                    CRITERION_HELPFULNESS,
                    CRITERION_CLINICAL_APPROPRIATENESS,
                    CRITERION_URGENCY_ACCURACY,
                    CRITERION_SPECIALIST_ROUTING,
                )
                criteria_map = [
                    (CRITERION_ANSWER_RELEVANCY,          "answer_relevancy"),
                    (CRITERION_FORMAT_CORRECTNESS,         "format_correctness"),
                    (CRITERION_HELPFULNESS,                "helpfulness"),
                    (CRITERION_CLINICAL_APPROPRIATENESS,   "clinical_appropriateness"),
                    (CRITERION_URGENCY_ACCURACY,           "urgency_accuracy"),
                    (CRITERION_SPECIALIST_ROUTING,         "specialist_routing"),
                ]
                for criterion_const, name in criteria_map:
                    judge_result = await evaluate_with_llm_judge(
                        input_text, agent_output, "synthesis", criterion_const
                    )
                    record["scores"][name] = judge_result.score
                    record["reasons"][name] = judge_result.reason[:300]
                    record["pass_fail"][name] = judge_result.score >= PASS_THRESHOLD
            except Exception as e:
                record["error"] = str(e)
        results.append(record)
        print(f"  [{case_id}] done")

    summary = _compute_summary(results)
    return {
        "timestamp": datetime.now().isoformat(),
        "use_llm_judge": use_llm_judge,
        "live_mode": live,
        "num_cases": len(results),
        "pass_threshold": PASS_THRESHOLD,
        "summary": summary,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Run evaluation benchmark")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM judge calls")
    parser.add_argument("--live", action="store_true", help="Run real graph instead of mock_output")
    parser.add_argument("--capture", action="store_true", help="Capture live outputs without LLM judge (для записи baseline)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of cases")
    parser.add_argument("--out", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    live_mode = args.live or args.capture
    use_judge = not args.no_llm and not args.capture

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "live" if live_mode else "mock"
    out_path = args.out or ARTIFACTS_DIR / f"benchmark_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    print(f"Running benchmark (mode={'live' if live_mode else 'mock'}, judge={'yes' if use_judge else 'no'})...")
    payload = asyncio.run(run_benchmark(use_llm_judge=use_judge, limit=args.limit, live=live_mode))

    print_results_table(payload.get("results", []), payload.get("summary", {}))

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Benchmark written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
