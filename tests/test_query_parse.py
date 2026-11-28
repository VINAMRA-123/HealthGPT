from datetime import date

import pytest

from app.ai.intent import classify_intent
from datetime import date
from app.ai.query_parse import (
    extract_day_offset,
    extract_days,
    extract_limit,
    extract_meal_type,
    has_day_range,
    resolve_date_range,
    wants_last_night,
)

TODAY = date(2026, 11, 28)  # a Saturday


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Show my last 3 meals", 3),
        ("What are my 10 most recent meals?", 10),
        ("give me my last five foods I ate", 5),
        ("Show my latest meals", 5),
        ("show my last 50 meals", 20),
    ],
)
def test_extract_limit(question, expected):
    assert extract_limit(question) == expected


def test_extract_meal_type():
    assert extract_meal_type("Did I have breakfast yesterday?") == "breakfast"
    assert extract_meal_type("Have I logged lunch today?") == "lunch"
    assert extract_meal_type("show my meals") is None


def test_day_offsets():
    assert extract_day_offset("what did I eat today") == 0
    assert extract_day_offset("protein yesterday") == 1
    assert extract_day_offset("what did I eat last night") == 1
    assert extract_day_offset("the day before yesterday") == 2
    assert wants_last_night("What did I eat last night?")


def test_extract_days_understands_words():
    assert extract_days("past seven days") == 7
    assert extract_days("last 2 weeks") == 14
    assert extract_days("nothing here") == 7


def test_has_day_range():
    assert has_day_range("how many meals this week")
    assert has_day_range("meals from the past seven days")
    assert not has_day_range("show my last 5 meals")


def test_this_week_is_week_to_date():
    first, after_last, label = resolve_date_range(
        "meals this week", TODAY
    )

    assert first == date(2026, 11, 23)
    assert after_last == date(2026, 11, 29)
    assert label == "this week so far"

def test_last_week_is_the_previous_calendar_week():
    first, after_last, label = resolve_date_range("meals last week", TODAY)
    assert first == date(2026, 11, 16)
    assert after_last == date(2026, 11, 23)


def test_past_n_days_ends_today():
    first, after_last, _ = resolve_date_range("meals from the past seven days", TODAY)
    assert first == date(2026, 11, 22)
    assert after_last == date(2026, 11, 29)


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Show my food log from yesterday.", "day_meals"),
        ("What did I eat last night?", "day_meals"),
        ("How many meals did I log this week?", "period_meals"),
        ("Give me meals from the past seven days.", "period_meals"),
        ("How much protein did I consume yesterday?", "daily_nutrition"),
        ("How much did I spend yesterday?", "daily_budget"),
        ("How much did I spend today?", "daily_budget"),
        ("How much did I spend on meals this week?", "weekly_budget"),
        ("Can I spend more today?", "llm"),
        ("Show my last 3 meals.", "recent_meals"),
    ],
)
def test_new_routes(question, expected):
    assert classify_intent(question) == expected



def test_this_week_returns_monday_through_today():
    start, end, label = resolve_date_range(
        "How much protein this week?",
        date(2026, 11, 28),  # Saturday
    )

    assert start == date(2026, 11, 23)
    assert end == date(2026, 11, 29)
    assert label == "this week so far"


def test_last_week_returns_previous_complete_week():
    start, end, label = resolve_date_range(
        "Show my nutrition last week",
        date(2026, 11, 28),
    )

    assert start == date(2026, 11, 16)
    assert end == date(2026, 11, 23)
    assert label == "last week"


def test_past_seven_days_includes_today():
    start, end, label = resolve_date_range(
        "Show my nutrition for the past 7 days",
        date(2026, 11, 28),
    )

    assert start == date(2026, 11, 22)
    assert end == date(2026, 11, 29)
    assert label == "the last 7 days"