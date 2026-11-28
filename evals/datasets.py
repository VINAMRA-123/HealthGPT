"""Labelled evaluation data for HealthGPT.

Labels describe what the *correct* behaviour is, not what the code currently
does. Add your own real questions here to make the numbers more convincing;
more cases means a more trustworthy percentage.

Intents:
    daily_nutrition   today's calories / macros          -> SQL
    period_nutrition  calories / macros over N days       -> SQL
    recent_meals      list of recently logged meals       -> SQL
    weekly_budget     spending against the weekly budget  -> SQL
    weekly_protein    protein this week                   -> SQL
    llm               reasoning, advice, general nutrition-> Gemini
"""

ROUTER_CASES: list[dict[str, str]] = [
    # ---- daily_nutrition ---------------------------------------------------
    {"question": "How many calories have I eaten today?", "expected": "daily_nutrition"},
    {"question": "How much protein did I consume today?", "expected": "daily_nutrition"},
    {"question": "What's my calorie intake today?", "expected": "daily_nutrition"},
    {"question": "calories today", "expected": "daily_nutrition"},
    {"question": "How many carbs have I had today?", "expected": "daily_nutrition"},
    {"question": "protein today", "expected": "daily_nutrition"},
    {"question": "How much fat did I eat today?", "expected": "daily_nutrition"},
    {"question": "How many calories did I log today?", "expected": "daily_nutrition"},
    {"question": "total calories I've had today", "expected": "daily_nutrition"},
    {"question": "carbs eaten today", "expected": "daily_nutrition"},
    {"question": "Calories consumed so far today", "expected": "daily_nutrition"},
    # ---- period_nutrition --------------------------------------------------
    {"question": "How much protein have I eaten in the last 3 days?", "expected": "period_nutrition"},
    {"question": "How many calories did I consume in the past week?", "expected": "period_nutrition"},
    {"question": "Calories I consumed over the previous 5 days", "expected": "period_nutrition"},
    {"question": "How many carbs in the last 10 days?", "expected": "period_nutrition"},
    {"question": "How much fat have I eaten recently?", "expected": "period_nutrition"},
    {"question": "protein intake over the past 2 weeks", "expected": "period_nutrition"},
    # ---- recent_meals ------------------------------------------------------
    {"question": "Show my latest logged meals", "expected": "recent_meals"},
    {"question": "What did I eat recently?", "expected": "recent_meals"},
    {"question": "List my recent meals", "expected": "recent_meals"},
    {"question": "meal history", "expected": "recent_meals"},
    {"question": "What foods have I logged lately?", "expected": "recent_meals"},
    {"question": "Show my food history", "expected": "recent_meals"},
    # ---- weekly_budget -----------------------------------------------------
    {"question": "How much of my weekly budget have I spent?", "expected": "weekly_budget"},
    {"question": "What's my remaining budget?", "expected": "weekly_budget"},
    {"question": "How much did I spend on food this week?", "expected": "weekly_budget"},
    {"question": "weekly spending", "expected": "weekly_budget"},
    {"question": "How much money have I spent this week?", "expected": "weekly_budget"},
    {"question": "Am I over budget this week?", "expected": "weekly_budget"},
    # ---- weekly_protein ----------------------------------------------------
    {"question": "How much protein this week?", "expected": "weekly_protein"},
    {"question": "weekly protein intake", "expected": "weekly_protein"},
    {"question": "Protein I've eaten this week", "expected": "weekly_protein"},
    {"question": "Did I meet my protein goal this week?", "expected": "weekly_protein"},
    # ---- day_meals: found while testing the deployed app -------------------
    {"question": "What did I eat yesterday?", "expected": "day_meals"},
    {"question": "How many meals did I log yesterday?", "expected": "day_meals"},
    {"question": "How many meals have I logged today?", "expected": "day_meals"},
    {"question": "How many calories did I have yesterday?", "expected": "day_meals"},
    # ---- daily_nutrition: phrasing found while testing ---------------------
    {"question": "Show my nutrition summary today", "expected": "daily_nutrition"},
    # ---- llm: advice with a day word must NOT be answered from SQL ---------
    {"question": "Can I eat rice today?", "expected": "llm"},
    {"question": "What should I eat today?", "expected": "llm"},
    # ---- llm: reasoning, advice and general knowledge ----------------------
    {"question": "Which of my recent meals had the most protein?", "expected": "llm"},
    {"question": "Compare my protein intake this week with last week", "expected": "llm"},
    {"question": "Suggest a high protein vegetarian dinner under 150 rupees", "expected": "llm"},
    {"question": "What should I eat to reach my protein goal?", "expected": "llm"},
    {"question": "Is oats healthy for weight loss?", "expected": "llm"},
    {"question": "How do I calculate my BMI?", "expected": "llm"},
    {"question": "Why did my weight go up?", "expected": "llm"},
    {"question": "Explain macros to me", "expected": "llm"},
    {"question": "Tell me about intermittent fasting", "expected": "llm"},
    {"question": "What are good sources of protein for vegetarians?", "expected": "llm"},
    {"question": "Hi", "expected": "llm"},
    {"question": "How many calories should I eat per day?", "expected": "llm"},
    {"question": "How much protein should I eat today?", "expected": "llm"},
    {"question": "Is it okay to eat late at night?", "expected": "llm"},
    # ---- llm: the cases the old substring router got wrong -----------------
    # "past" inside "pasta"
    {"question": "How many calories are in pasta?", "expected": "llm"},
    # "ate" inside "latest"
    {"question": "What is the latest research on protein?", "expected": "llm"},
]


# A record is "flagged" when it has missing, invalid, or inconsistent values.
VALIDATOR_CASES: list[dict] = [
    {
        "name": "consistent meal",
        "meal": {"calories": 265, "protein_g": 18, "carbs_g": 6, "fat_g": 20},
        "expected": "valid",
    },
    {
        "name": "decimal values within tolerance",
        "meal": {"calories": 250, "protein_g": 12, "carbs_g": 40, "fat_g": 8},
        "expected": "valid",
    },
    {
        "name": "zero everything (e.g. water)",
        "meal": {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0},
        "expected": "valid",
    },
    {
        "name": "small drink",
        "meal": {"calories": 30, "protein_g": 1, "carbs_g": 5, "fat_g": 1},
        "expected": "valid",
    },
    {
        "name": "calories far below macros",
        "meal": {"calories": 10, "protein_g": 20, "carbs_g": 10, "fat_g": 30},
        "expected": "flagged",
    },
    {
        "name": "calories far above macros",
        "meal": {"calories": 400, "protein_g": 20, "carbs_g": 50, "fat_g": 0},
        "expected": "flagged",
    },
    {
        "name": "zero calories with macros",
        "meal": {"calories": 0, "protein_g": 10, "carbs_g": 10, "fat_g": 5},
        "expected": "flagged",
    },
    {
        "name": "missing protein",
        "meal": {"calories": 200, "protein_g": None, "carbs_g": 30, "fat_g": 5},
        "expected": "flagged",
    },
    {
        "name": "missing field entirely",
        "meal": {"calories": 200, "carbs_g": 30, "fat_g": 5},
        "expected": "flagged",
    },
    {
        "name": "negative calories",
        "meal": {"calories": -5, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        "expected": "flagged",
    },
    {
        "name": "boolean instead of number",
        "meal": {"calories": True, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        "expected": "flagged",
    },
    {
        "name": "string instead of number",
        "meal": {"calories": "200", "protein_g": 10, "carbs_g": 20, "fat_g": 5},
        "expected": "flagged",
    },
    {
        "name": "NaN value",
        "meal": {"calories": float("nan"), "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        "expected": "flagged",
    },
    {
        "name": "infinite value",
        "meal": {"calories": float("inf"), "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        "expected": "flagged",
    },
    {
        "name": "overflowing macros",
        "meal": {"calories": 100, "protein_g": 1e308, "carbs_g": 1, "fat_g": 1},
        "expected": "flagged",
    },
    {
        "name": "record is not an object",
        "meal": "not a meal",
        "expected": "flagged",
    },
]
