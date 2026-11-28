"""Small, dependency-free helpers that read dates, counts and meal types out
of a question, so the SQL handlers can answer exactly what was asked.

Everything here is pure (no database, no clock unless a date is passed in),
which keeps it easy to unit test.
"""

import re
from datetime import date, timedelta

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fourteen": 14, "fifteen": 15, "twenty": 20,
    "thirty": 30,
}

_NUM = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


def _normalize(message: str) -> str:
    text = re.sub(r"\s+", " ", (message or "").lower().strip())
    return re.sub(r"[’']", "'", text)


def _to_int(token: str) -> int:
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def extract_limit(message: str, default: int = 5, maximum: int = 20) -> int:
    """How many meals the user asked for: "last 3 meals", "10 most recent"."""
    text = _normalize(message)

    patterns = (
        rf"(?:last|past|latest|recent|previous)\s+{_NUM}\s+"
        r"(?:meals?|foods?|entries|items|things)",
        rf"{_NUM}\s+(?:most\s+recent|latest|recent|last)\s+"
        r"(?:meals?|foods?|entries|items)?",
        rf"(?:last|past|latest)\s+{_NUM}\b(?!\s+(?:days?|weeks?|hours?))",
    )

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return max(1, min(_to_int(match.group(1)), maximum))

    return default


def extract_meal_type(message: str) -> str | None:
    """breakfast / lunch / dinner / snack if the question names one."""
    text = _normalize(message)

    for meal_type in MEAL_TYPES:
        if re.search(rf"(?<![a-z]){meal_type}s?(?![a-z])", text):
            return meal_type

    return None


def extract_day_offset(message: str) -> int:
    """0 = today, 1 = yesterday, 2 = the day before yesterday."""
    text = _normalize(message)

    if "day before yesterday" in text:
        return 2

    if "yesterday" in text or "last night" in text:
        return 1

    return 0


def wants_last_night(message: str) -> bool:
    return "last night" in _normalize(message)


def extract_days(message: str, default: int = 7) -> int:
    """Number of days for "last 14 days", "past seven days", "2 weeks"."""
    text = _normalize(message)

    match = re.search(rf"(?:last|past|previous|for)\s+{_NUM}\s+days?", text)

    if match:
        return max(1, min(_to_int(match.group(1)), 365))

    match = re.search(rf"(?:last|past|previous|for)\s+{_NUM}\s+weeks?", text)

    if match:
        return max(1, min(_to_int(match.group(1)) * 7, 365))

    if "fortnight" in text or "two weeks" in text:
        return 14

    return default


def has_day_range(message: str) -> bool:
    """True for "this week", "last week", "past 7 days", "past seven days"."""
    text = _normalize(message)

    return bool(
        re.search(rf"(?:last|past|previous)\s+{_NUM}\s+(?:days?|weeks?)", text)
        or re.search(
            r"\b(?:this|last|past|previous)\s+week\b|\bfortnight\b", text
        )
    )


def resolve_date_range(
    message: str, today: date
) -> tuple[date, date, str]:
    """Return (start date, exclusive end date, period label).

    "this week"       -> Monday through today
    "last week"       -> previous Monday through Sunday
    "past 7 days"     -> today and preceding 6 calendar days
    "last 14 days"    -> today and preceding 13 calendar days
    """
    text = _normalize(message)

    has_number = re.search(
        rf"(?:last|past|previous|for)\s+{_NUM}\s+(?:days?|weeks?)",
        text,
    )

    if not has_number and re.search(r"\bthis week\b", text):
        monday = today - timedelta(days=today.weekday())
        return monday, today + timedelta(days=1), "this week so far"

    if not has_number and re.search(r"\b(?:last|previous) week\b", text):
        monday = today - timedelta(days=today.weekday()) - timedelta(days=7)
        return monday, monday + timedelta(days=7), "last week"

    days = extract_days(text)
    start = today - timedelta(days=days - 1)

    return start, today + timedelta(days=1), f"the last {days} days"