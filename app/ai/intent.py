"""Intent router: decides which questions are answered straight from SQL.

The rules and their order are the same as the original substring router, but
terms are now matched as whole words. The old router had false positives such
as:

    "ate"  matching inside "latest", "update", "late"
    "past" matching inside "pasta"
    "fat"  matching inside "fatigue"

so "How many calories are in pasta?" was treated as a query over the user's
logged meals instead of being sent to the LLM.
"""

import re
from functools import lru_cache

from app.ai.query_parse import has_day_range

# --- Questions that need reasoning always go to the LLM. ---------------------
# Matched as word *prefixes* so "calculated", "suggestions", "explained" count.
ANALYTICAL_PREFIXES = (
    "analyze",
    "analyse",
    "compare",
    "which meal",
    "most protein",
    "highest protein",
    "least protein",
    "total protein",
    "calculate",
    "recommend",
    "suggest",
    "what should i eat",
    "should i",
    "how can i",
    "how do i",
    "how to",
    "how can i reach",
    "how to reach",
    "based on my",
    "why did",
    "can i ",
    "explain",
)

# --- Everything below is matched as whole words / phrases. -------------------
NUTRIENTS = (
    "calorie",
    "calories",
    "kcal",
    "protein",
    "proteins",
    "carb",
    "carbs",
    "carbohydrate",
    "carbohydrates",
    "fat",
    "fats",
)

TODAY = ("today", "today's", "this day")

# Days the daily nutrition / budget handlers can answer for.
DAY_REF = TODAY + ("yesterday", "yesterday's")

INTAKE = (
    "consumed",
    "consume",
    "eaten",
    "ate",
    "eat",
    "eating",
    "intake",
    "log",
    "logged",
    "have i had",
    "had",
)

PERIOD = ("last", "past", "previous", "recent", "recently")

PERIOD_INTAKE = INTAKE + ("how much", "how many")

MEALS = ("meal", "meals", "food", "foods", "ate", "eaten", "eat", "eating")

RECENT_TIME = (
    "recent",
    "recently",
    "latest",
    "logged",
    "history",
    "last",
)

BUDGET = (
    "budget",
    "budgets",
    "spending",
    "spent",
    "spend",
    "expense",
    "expenses",
)

WEEKLY = ("week", "weeks", "weekly", "this week", "remaining")

PROTEIN = ("protein", "proteins")

WEEKLY_PERIOD = ("week", "weeks", "weekly", "this week")

DAILY_PHRASES = (
    "calories today",
    "today's calories",
    "calories have i eaten",
    "calories did i eat",
    "how many calories have i had today",
    "how many calories did i consume today",
    "protein today",
    "protein have i eaten",
    "protein did i eat",
    "how much protein have i had today",
    "how much protein did i consume today",
)

NUTRITION_SUMMARY = (
    "nutrition summary",
    "nutritional summary",
    "summary of my nutrition",
    "my nutrition",
)

# "yesterday" / "today" questions about which meals were logged. Phrases are
# past-tense lookups on purpose, so advice such as "Can I eat rice today?"
# still goes to the LLM.
DAY_WORDS = (
    "yesterday",
    "yesterday's",
    "today",
    "today's",
    "last night",
)

DAY_MEAL_PHRASES = (
    "did i eat",
    "did i log",
    "did i have",
    "have i eaten",
    "have i logged",
    "have i had",
    "i ate",
    "i logged",
    "i had",
    "i've eaten",
    "i've logged",
    "how many meals",
    "how many foods",
    "my meals",
    "show my meals",
    "list my meals",
    "food log",
    "food entries",
    "food diary",
    "show my food",

    # Additional natural-language variations
    "yesterday meals",
    "yesterday's meals",
    "meals yesterday",
    "foods yesterday",
    "yesterday food",
    "yesterday's food",
    "today meals",
    "today's meals",
    "meals today",
    "foods today",
)

# Lookups over a longer period: "how many meals this week",
# "meals from the past seven days", "what did I eat last week".
PERIOD_MEAL_PHRASES = (
    "how many meals",
    "how many foods",
    "my meals",
    "show my meals",
    "list my meals",
    "list meals",
    "give me meals",
    "give me my meals",
    "show meals",
    "meals from",
    "meals in",
    "meals during",
    "meals i logged",
    "meals did i",
    "food log",
    "food entries",
    "food diary",
    "foods did i",
    "did i eat",
    "did i log",
    "i ate",
    "i logged",
    "i've eaten",
    "have i eaten",
    "have i logged",
)

@lru_cache(maxsize=None)
def _pattern(terms: tuple[str, ...], prefix: bool) -> re.Pattern:
    # Longest terms first so "this week" wins over "this".
    alternatives = "|".join(
        re.escape(term) for term in sorted(terms, key=len, reverse=True)
    )
    tail = "" if prefix else r"(?![a-z0-9])"
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives}){tail}")


def _has(text: str, terms: tuple[str, ...], *, prefix: bool = False) -> bool:
    return _pattern(terms, prefix).search(text) is not None


def classify_intent(message: str) -> str:
    """Return one of: daily_nutrition, daily_budget, period_nutrition,
    day_meals, period_meals, recent_meals, weekly_budget, weekly_protein,
    llm."""
    if not isinstance(message, str):
        return "llm"

    text = re.sub(r"\s+", " ", message.lower().strip())
    text = re.sub(r"[’']", "'", text)

    if _has(text, ANALYTICAL_PREFIXES, prefix=True):
        return "llm"

    has_nutrient = _has(text, NUTRIENTS)

    if has_nutrient and _has(text, DAY_REF) and _has(text, INTAKE):
        return "daily_nutrition"

    if _has(text, NUTRITION_SUMMARY) and _has(text, TODAY):
        return "daily_nutrition"

    if has_nutrient and _has(text, PERIOD) and _has(text, PERIOD_INTAKE):
        return "period_nutrition"

    if (
        _has(text, DAY_WORDS)
        and _has(text, DAY_MEAL_PHRASES)
        and not _has(text, BUDGET)
    ):
        return "day_meals"

    # "How many meals did I log this week?", "meals from the past 7 days".
    if (
        has_day_range(text)
        and _has(text, MEALS)
        and _has(text, PERIOD_MEAL_PHRASES)
        and not _has(text, BUDGET)
        and not has_nutrient
    ):
        return "period_meals"

    # "How much did I spend yesterday?" (this week is weekly_budget below).
    if (
        _has(text, BUDGET)
        and _has(text, DAY_REF)
        and not _has(text, WEEKLY)
    ):
        return "daily_budget"

    if _has(text, MEALS) and _has(text, RECENT_TIME):
        return "recent_meals"

    if _has(text, BUDGET) and _has(text, WEEKLY):
        return "weekly_budget"

    if _has(text, PROTEIN) and _has(text, WEEKLY_PERIOD):
        return "weekly_protein"

    if _has(text, DAILY_PHRASES):
        return "daily_nutrition"

    return "llm"
