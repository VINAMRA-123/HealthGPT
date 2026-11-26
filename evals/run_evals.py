"""Run HealthGPT's offline evaluations.

    python -m evals.run_evals                  # print results
    python -m evals.run_evals --json out.json  # also save them
    python -m evals.run_evals --langsmith      # also upload experiments

No database, Gemini key or network is needed for the default run.
With --langsmith you need LANGSMITH_API_KEY; the router questions (synthetic,
no user data) are uploaded as a dataset and each router is scored as an
experiment you can open and compare in the LangSmith UI.
"""

import argparse
import json
import os
import sys
from collections import Counter
from typing import Callable

# app.api.chat reads settings at import time; real values still win.
os.environ.setdefault("SUPABASE_URL", "https://example-project.supabase.co")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)

from app.ai.agents.nutrition_validator import validate_meals  # noqa: E402
from app.ai.intent import classify_intent  # noqa: E402
from evals.datasets import ROUTER_CASES, VALIDATOR_CASES  # noqa: E402

LLM_INTENT = "llm"


def _pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def evaluate_router(name: str, predict: Callable[[str], str]) -> dict:
    predictions = [
        (case, predict(case["question"])) for case in ROUTER_CASES
    ]
    correct = sum(1 for case, got in predictions if got == case["expected"])

    intents = sorted({case["expected"] for case in ROUTER_CASES} | {
        got for _, got in predictions
    })
    per_intent = {}

    for intent in intents:
        true_positive = sum(
            1 for case, got in predictions
            if got == intent and case["expected"] == intent
        )
        predicted = sum(1 for _, got in predictions if got == intent)
        actual = sum(1 for case, _ in predictions if case["expected"] == intent)
        per_intent[intent] = {
            "precision": _pct(true_positive, predicted),
            "recall": _pct(true_positive, actual),
            "support": actual,
        }

    # Wrongly sending a general question to SQL answers it from the user's own
    # meal log, which is the costly mistake.
    llm_sent_to_sql = sum(
        1 for case, got in predictions
        if case["expected"] == LLM_INTENT and got != LLM_INTENT
    )
    sql_sent_to_llm = sum(
        1 for case, got in predictions
        if case["expected"] != LLM_INTENT and got == LLM_INTENT
    )

    return {
        "name": name,
        "cases": len(predictions),
        "correct": correct,
        "accuracy_pct": _pct(correct, len(predictions)),
        "general_questions_wrongly_sent_to_sql": llm_sent_to_sql,
        "data_questions_missed_by_sql": sql_sent_to_llm,
        "per_intent": per_intent,
        "failures": [
            {
                "question": case["question"],
                "expected": case["expected"],
                "got": got,
            }
            for case, got in predictions
            if got != case["expected"]
        ],
    }


def evaluate_validator() -> dict:
    rows = []

    for case in VALIDATOR_CASES:
        result = validate_meals([case["meal"]])[0]
        rows.append((case, result["data_quality_status"]))

    correct = sum(1 for case, got in rows if got == case["expected"])
    true_positive = sum(
        1 for case, got in rows
        if got == "flagged" and case["expected"] == "flagged"
    )
    predicted_flagged = sum(1 for _, got in rows if got == "flagged")
    actual_flagged = sum(1 for case, _ in rows if case["expected"] == "flagged")

    return {
        "cases": len(rows),
        "correct": correct,
        "accuracy_pct": _pct(correct, len(rows)),
        "flagged_precision_pct": _pct(true_positive, predicted_flagged),
        "flagged_recall_pct": _pct(true_positive, actual_flagged),
        "failures": [
            {"name": case["name"], "expected": case["expected"], "got": got}
            for case, got in rows
            if got != case["expected"]
        ],
    }


def dataset_composition() -> dict:
    counts = Counter(case["expected"] for case in ROUTER_CASES)
    sql = sum(n for intent, n in counts.items() if intent != LLM_INTENT)

    return {
        "by_intent": dict(counts),
        "sql_answerable_pct_of_test_set": _pct(sql, len(ROUTER_CASES)),
    }


def print_router(report: dict) -> None:
    print(f"\n{report['name']}")
    print(
        f"  accuracy: {report['correct']}/{report['cases']} "
        f"= {report['accuracy_pct']}%"
    )
    print(
        "  general questions wrongly answered from SQL: "
        f"{report['general_questions_wrongly_sent_to_sql']}"
    )
    print(
        "  data questions missed (sent to the LLM instead of SQL): "
        f"{report['data_questions_missed_by_sql']}"
    )

    for intent, stats in report["per_intent"].items():
        print(
            f"    {intent:<17} precision {stats['precision']:>5}%  "
            f"recall {stats['recall']:>5}%  (n={stats['support']})"
        )

    for failure in report["failures"]:
        print(
            f"    x {failure['question']!r}: expected "
            f"{failure['expected']}, got {failure['got']}"
        )


def push_to_langsmith(routers: dict[str, Callable[[str], str]]) -> None:
    """Upload the router dataset and one experiment per router."""
    try:
        from langsmith import Client, evaluate
    except Exception as exc:  # pragma: no cover
        print(f"\nLangSmith not available: {exc}")
        return

    if not os.getenv("LANGSMITH_API_KEY"):
        print("\nSet LANGSMITH_API_KEY to use --langsmith.")
        return

    dataset_name = "healthgpt-intent-routing"
    client = Client()

    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Labelled user questions and the intent each should route to.",
        )
        client.create_examples(
            dataset_id=dataset.id,
            inputs=[{"question": case["question"]} for case in ROUTER_CASES],
            outputs=[{"intent": case["expected"]} for case in ROUTER_CASES],
        )
        print(f"\nCreated LangSmith dataset '{dataset_name}'.")

    def intent_matches(outputs: dict, reference_outputs: dict) -> bool:
        return outputs["intent"] == reference_outputs["intent"]

    for label, predict in routers.items():

        def target(inputs: dict, predict=predict) -> dict:
            return {"intent": predict(inputs["question"])}

        evaluate(
            target,
            data=dataset_name,
            evaluators=[intent_matches],
            experiment_prefix=f"router-{label}",
            max_concurrency=4,
        )

    print("Experiments uploaded. Open LangSmith > Datasets & Experiments.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="write the full results to this file")
    parser.add_argument(
        "--langsmith",
        action="store_true",
        help="upload the router dataset and experiments to LangSmith",
    )
    args = parser.parse_args()

    routers: dict[str, Callable[[str], str]] = {"word-boundary": classify_intent}
    reports = {}

    try:
        from app.api.chat import classify_intent_legacy

        routers = {"substring-legacy": classify_intent_legacy, **routers}
    except Exception as exc:
        print(
            "Could not import the legacy router "
            f"({type(exc).__name__}: {exc}); comparing the new router only."
        )

    for label, predict in routers.items():
        reports[label] = evaluate_router(f"Router: {label}", predict)
        print_router(reports[label])

    validator = evaluate_validator()
    print(
        f"\nNutrition validator: {validator['correct']}/{validator['cases']} "
        f"correct ({validator['accuracy_pct']}%), flagged precision "
        f"{validator['flagged_precision_pct']}%, recall "
        f"{validator['flagged_recall_pct']}%"
    )

    for failure in validator["failures"]:
        print(
            f"    x {failure['name']}: expected {failure['expected']}, "
            f"got {failure['got']}"
        )

    composition = dataset_composition()
    print(
        f"\nTest set: {len(ROUTER_CASES)} routing questions, "
        f"{composition['sql_answerable_pct_of_test_set']}% answerable from SQL "
        "(this describes the test set, NOT real traffic; get the real share "
        "from LangSmith tags path:sql / path:llm)."
    )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "routers": reports,
                    "validator": validator,
                    "composition": composition,
                },
                handle,
                indent=2,
            )

        print(f"Saved results to {args.json}")

    if args.langsmith:
        push_to_langsmith(routers)

    return 0


if __name__ == "__main__":
    sys.exit(main())
