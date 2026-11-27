"""Scope guardrail: HealthGPT only talks about nutrition, food, fitness and
the user's own meal / budget tracking.

Two layers keep it on topic:

1. This module (free, instant, no LLM call). It blocks questions that are
   clearly unrelated (entertainment, sports, politics, coding, finance, trivia,
   creative writing...) and answers them with a fixed reply.
2. A strict scope rule in the Gemini system prompt, for everything this module
   cannot judge with certainty (``"uncertain"``), such as short follow-ups.

Blocking is deliberately conservative: a message is refused here only when it
matches an unrelated topic and has no health vocabulary. Unknown messages are
passed on to layer 2 instead of being refused, so real questions are not
rejected just because a food or word is missing from the lists below.
"""

import re
from functools import lru_cache

from app.ai.intent import classify_intent

IN_SCOPE = "in_scope"
OFF_TOPIC = "off_topic"
UNCERTAIN = "uncertain"

OFF_TOPIC_REPLY = (
    "I'm HealthGPT, so I can only help with nutrition, food, fitness and "
    "your meal and budget tracking. I can't help with that topic.\n\n"
    "You could ask me things like:\n"
    "- How much protein have I eaten today?\n"
    "- Suggest a high-protein vegetarian dinner under ₹150.\n"
    "- How much of my weekly food budget have I spent?"
)

# Creative, coding and homework requests are refused even when they mention
# food ("write a song about protein", "python code to track calories").
TASK_DENY = (
    "poem",
    "poetry",
    "song",
    "songs",
    "lyrics",
    "joke",
    "jokes",
    "riddle",
    "story",
    "stories",
    "essay",
    "homework",
    "python",
    "javascript",
    "java",
    "coding",
    "code",
    "translate",
    "horoscope",
    "astrology",
)

# Clearly unrelated subjects.
TOPIC_DENY = (
    "movie",
    "movies",
    "film",
    "films",
    "netflix",
    "music",
    "concert",
    "concerts",
    "tour",
    "album",
    "singer",
    "actor",
    "actress",
    "celebrity",
    "bollywood",
    "hollywood",
    "cricket",
    "ipl",
    "football",
    "soccer",
    "tennis",
    "nba",
    "fifa",
    "election",
    "elections",
    "politics",
    "politician",
    "prime minister",
    "president",
    "parliament",
    "stock",
    "stocks",
    "crypto",
    "bitcoin",
    "forex",
    "sensex",
    "nifty",
    "share market",
    "news",
    "programming",
    "algorithm",
    "debug",
    "flight",
    "flights",
    "hotel",
    "hotels",
    "visa",
    "iphone",
    "laptop",
    "gaming",
    "video game",
    "pubg",
    "minecraft",
    "lottery",
    "capital of",
    "weather",
)

# Health vocabulary that matches whole words only.
ALLOW_WORDS = (
    "eat", "eats", "eating", "eaten", "ate",
    "fat", "fats", "carb", "carbs", "fiber", "fibre",
    "sugar", "salt", "sodium", "oil", "ghee", "butter",
    "rice", "roti", "chapati", "dal", "paneer", "oats", "egg", "eggs",
    "chicken", "fish", "milk", "curd", "dahi", "fruit", "fruits",
    "vegetable", "vegetables", "banana", "apple", "nuts", "almonds",
    "seeds", "tofu", "soy", "lentil", "lentils", "quinoa", "bread",
    "pasta", "noodles", "maggi", "chocolate", "spinach", "potato",
    "tomato", "onion", "poha", "idli", "dosa", "upma", "paratha",
    "khichdi", "sambar", "rajma", "chole", "biryani", "samosa", "pizza",
    "burger", "sweet", "sweets", "dessert",
    "tea", "coffee", "juice", "water", "drink", "drinks",
    "bmi", "bp", "gym", "yoga", "walk", "walking", "run", "running",
    "steps", "sleep", "log", "logged", "dashboard", "goal", "goals",
    "target", "targets", "serving", "servings", "gram", "grams", "kg",
    "lose", "gain", "bulk", "keto", "paleo", "doctor", "symptom",
    "symptoms", "medicine", "pcos", "thyroid", "spent",
)

# Health vocabulary matched as word *prefixes* (nutri -> nutrition, nutrient).
ALLOW_STEMS = (
    "nutri", "calor", "kcal", "protein", "carbo", "vitamin", "mineral",
    "diet", "meal", "food", "hydrat", "supplement", "ingredient",
    "vegetar", "vegan", "allerg", "gluten", "lactose", "diabet",
    "cholest", "glucos", "metabol", "digest", "workout", "exercis",
    "fitness", "health", "weigh", "macro", "portion", "breakfast",
    "lunch", "dinner", "snack", "recipe", "cook", "fasting", "budget",
    "spend", "expens", "hungry", "hunger", "appetite", "cravin", "obes",
    "drink",
)

GREETINGS = (
    "hi", "hii", "hello", "hey", "thanks", "thank you", "thankyou", "ok",
    "okay", "help", "good morning", "good afternoon", "good evening",
    "bye", "who are you", "what can you do", "what do you do",
    "how are you",
)

MAX_GREETING_WORDS = 8


@lru_cache(maxsize=None)
def _pattern(terms: tuple[str, ...], prefix: bool) -> re.Pattern:
    alternatives = "|".join(
        re.escape(term) for term in sorted(terms, key=len, reverse=True)
    )
    tail = "" if prefix else r"(?![a-z0-9])"
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives}){tail}")


def _has(text: str, terms: tuple[str, ...], *, prefix: bool = False) -> bool:
    return _pattern(terms, prefix).search(text) is not None


def check_scope(message: str) -> str:
    """Return ``in_scope``, ``off_topic`` or ``uncertain`` for a message."""
    if not isinstance(message, str):
        return UNCERTAIN

    text = re.sub(r"\s+", " ", message.lower().strip())
    text = re.sub(r"[’']", "'", text)

    if not text:
        return UNCERTAIN

    if _has(text, TASK_DENY):
        return OFF_TOPIC

    if _has(text, ALLOW_WORDS) or _has(text, ALLOW_STEMS, prefix=True):
        return IN_SCOPE

    if _has(text, TOPIC_DENY):
        return OFF_TOPIC

    if len(text.split()) <= MAX_GREETING_WORDS and _has(text, GREETINGS):
        return IN_SCOPE

    return UNCERTAIN


def classify_request(message: str) -> str:
    """Intent for a request, including ``off_topic`` for blocked questions."""
    if check_scope(message) == OFF_TOPIC:
        return OFF_TOPIC

    return classify_intent(message)
