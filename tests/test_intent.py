"""Tests for the word-boundary intent router."""

import pytest

from app.ai.intent import classify_intent
from evals.datasets import ROUTER_CASES


@pytest.mark.parametrize(
    "question, expected",
    [
        # The substring bugs the old router had.
        ("How many calories are in pasta?", "llm"),
        ("What is the latest research on protein?", "llm"),
        ("I feel fatigued, any advice?", "llm"),
        # Behaviour that must keep working.
        ("How many calories have I eaten today?", "daily_nutrition"),
        ("How much protein have I eaten in the last 3 days?", "period_nutrition"),
        ("Show my latest logged meals", "recent_meals"),
        ("How much of my weekly budget have I spent?", "weekly_budget"),
        ("How much protein this week?", "weekly_protein"),
        ("Compare my protein intake this week with last week", "llm"),
                # Natural-language variations for meal lookups.
        ("give my yesterday meals?", "day_meals"),
        ("what foods did I eat yesterday?", "day_meals"),
        ("What did I eat today?", "day_meals"),
        ("Show my meals from yesterday", "day_meals"),

        # Recent food lookup variations.
        ("give me my last five foods I ate", "recent_meals"),
        ("show my last 5 foods", "recent_meals"),
        ("List my latest meals", "recent_meals"),
        ("Show my recent food history", "recent_meals"),

        # General nutrition questions must not trigger SQL.
        ("What foods are high in protein?", "llm"),
        ("Which meal has the highest protein?", "llm"),
        ("Can I eat pasta today?", "llm"),
        ("What foods contain healthy fats?", "llm"),

        # Period nutrition.
        ("How much protein did I consume last week?", "period_nutrition"),
    ],
)
def test_key_routing_cases(question, expected):
    assert classify_intent(question) == expected


def test_matching_ignores_case_spacing_and_curly_apostrophes():
    assert classify_intent("  CALORIES   TODAY  ") == "daily_nutrition"
    assert classify_intent("What’s my calorie intake today?") == "daily_nutrition"


def test_non_string_input_goes_to_the_llm():
    assert classify_intent(None) == "llm"  # type: ignore[arg-type]


def test_labelled_dataset_accuracy_stays_high():
    wrong = [
        (case["question"], case["expected"], classify_intent(case["question"]))
        for case in ROUTER_CASES
        if classify_intent(case["question"]) != case["expected"]
    ]
    accuracy = 1 - len(wrong) / len(ROUTER_CASES)

    # A little slack so one new, hard question does not break the build.
    assert accuracy >= 0.9, f"routing regressed, misses: {wrong}"
