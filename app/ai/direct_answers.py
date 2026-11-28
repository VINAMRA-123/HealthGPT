"""Answers built straight from the database (no LLM).

Every handler follows the same rules:

* Dates are India (IST) calendar days, converted to UTC for the query.
* Nutrition totals use only meals that pass ``validate_meals``. Flagged
  meals are listed and called out, never silently added to a total.
* Costs are summed over all meals: a nutrition flag does not make the
  recorded price wrong.
* Times shown to the user are in IST.
"""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.agents.nutrition_validator import validate_meals
from app.ai.query_parse import (
    extract_day_offset,
    extract_limit,
    extract_meal_type,
    resolve_date_range,
    wants_last_night,
)
from app.models import HealthProfile, MealLog

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

MAX_LISTED_MEALS = 30

INCOMPLETE_NOTE = (
    "These figures cover logged meals only and may not reflect "
    "everything you ate."
)


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------

def _f(value) -> float | None:
    """Decimal / int / None -> float / None (never turns None into 0)."""
    return float(value) if value is not None else None


def today_ist() -> date:
    return datetime.now(IST).date()


def ist_bounds_to_utc(
    start: datetime, end: datetime
) -> tuple[datetime, datetime]:
    return start.astimezone(UTC), end.astimezone(UTC)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC start and end of one IST calendar day."""
    start = datetime.combine(day, time.min, tzinfo=IST)
    return ist_bounds_to_utc(start, start + timedelta(days=1))


def range_bounds(first: date, day_after_last: date) -> tuple[datetime, datetime]:
    start = datetime.combine(first, time.min, tzinfo=IST)
    end = datetime.combine(day_after_last, time.min, tzinfo=IST)
    return ist_bounds_to_utc(start, end)


def last_night_bounds(today: date) -> tuple[datetime, datetime]:
    """6 PM yesterday to 6 AM today, India time."""
    start = datetime.combine(
        today - timedelta(days=1), time(18, 0), tzinfo=IST
    )
    end = datetime.combine(today, time(6, 0), tzinfo=IST)
    return ist_bounds_to_utc(start, end)


def to_ist(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)

    return moment.astimezone(IST)


def format_ist(moment: datetime | None) -> str:
    local = to_ist(moment)

    if local is None:
        return "time not recorded"

    return local.strftime("%d %b, %I:%M %p").lstrip("0")


def calories_text(value: float | None) -> str:
    return f"{value:.0f} kcal" if value is not None else "calories not recorded"


def query_meals(
    db: Session,
    user_id: UUID,
    start_utc: datetime,
    end_utc: datetime,
    meal_type: str | None = None,
) -> list[MealLog]:
    query = db.query(MealLog).filter(
        MealLog.user_id == user_id,
        MealLog.consumed_at >= start_utc,
        MealLog.consumed_at < end_utc,
    )

    if meal_type:
        query = query.filter(func.lower(MealLog.meal_type) == meal_type)

    return query.order_by(MealLog.consumed_at.asc()).all()


def validated_rows(meals) -> list[dict]:
    """Meal rows with data-quality status attached by ``validate_meals``."""
    return validate_meals(
        [
            {
                "food_name": meal.food_name,
                "meal_type": meal.meal_type,
                "portion": meal.portion,
                "calories": _f(meal.calories),
                "protein_g": _f(meal.protein_g),
                "carbs_g": _f(meal.carbs_g),
                "fat_g": _f(meal.fat_g),
                "cost": _f(meal.cost),
                "consumed_at": meal.consumed_at,
            }
            for meal in meals
        ]
    )


def summarize_validated(rows: list[dict]) -> dict:
    """Nutrition totals over valid meals only, plus counts."""
    totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    valid = 0
    flagged = 0

    for row in rows:
        if row.get("data_quality_status") == "flagged":
            flagged += 1
            continue

        valid += 1

        for field in totals:
            totals[field] += row.get(field) or 0.0

    return {**totals, "valid_count": valid, "flagged_count": flagged}


def flagged_note(flagged_count: int) -> str:
    return (
        f"{flagged_count} meal(s) were left out of the nutrition totals "
        "because their recorded values look inconsistent. Their costs "
        "are still counted."
    )


def meal_line(row: dict, *, with_time: bool = False, with_date: bool = False) -> str:
    flag = (
        " (flagged: nutrition values look inconsistent)"
        if row.get("data_quality_status") == "flagged"
        else ""
    )

    when = ""

    if with_date or with_time:
        local = to_ist(row.get("consumed_at"))

        if local is not None:
            pattern = "%d %b, %I:%M %p" if with_time else "%d %b"
            when = f"{local.strftime(pattern).lstrip('0')}: "

    portion = row.get("portion") or "not recorded"

    return (
        f"- {when}{row['food_name']} ({row['meal_type']}), "
        f"portion: {portion}, {calories_text(row.get('calories'))}{flag}"
    )


def latest_profile(db: Session, user_id: UUID):
    return (
        db.query(HealthProfile)
        .filter(HealthProfile.user_id == user_id)
        .order_by(HealthProfile.id.desc())
        .first()
    )


def day_label(offset: int) -> str:
    return {0: "today", 1: "yesterday"}.get(offset, "the day before yesterday")


# ------------------------------------------------------------------
# Handlers
# ------------------------------------------------------------------

def answer_recent_meals(db: Session, user_id: UUID, message: str) -> dict:
    limit = extract_limit(message)

    meals = (
        db.query(MealLog)
        .filter(MealLog.user_id == user_id)
        .order_by(MealLog.consumed_at.desc())
        .limit(limit)
        .all()
    )

    if not meals:
        return {
            "answer": "You have no logged meals yet.",
            "model": "sql",
            "meals_considered": 0,
            "meals": [],
        }

    rows = validated_rows(meals)
    summary = summarize_validated(rows)

    answer = (
        f"Here are your {len(meals)} most recent logged meal(s) "
        "(times in IST):\n"
        + "\n".join(meal_line(row, with_time=True) for row in rows)
    )

    if summary["flagged_count"]:
        answer += "\n\n" + flagged_note(summary["flagged_count"])

    structured = [
        {
            "food_name": meal.food_name,
            "meal_type": meal.meal_type,
            "portion": meal.portion,
            "calories": _f(meal.calories),
            "protein_g": _f(meal.protein_g),
            "carbs_g": _f(meal.carbs_g),
            "fat_g": _f(meal.fat_g),
            "cost": _f(meal.cost),
            "consumed_at": (
                to_ist(meal.consumed_at).isoformat()
                if meal.consumed_at is not None
                else None
            ),
        }
        for meal in meals
    ]

    return {
        "answer": answer,
        "model": "sql",
        "meals_considered": len(meals),
        "meals": structured,
    }


def answer_daily_nutrition(db: Session, user_id: UUID, message: str) -> dict:
    offset = extract_day_offset(message)
    label = day_label(offset)
    day = today_ist() - timedelta(days=offset)

    meals = query_meals(db, user_id, *day_bounds(day))

    if not meals:
        return {
            "answer": (
                f"You haven't logged any meals {label}, so I can't "
                "calculate your intake. Log your meals to see daily totals."
            ),
            "model": "sql",
            "meals_considered": 0,
        }

    summary = summarize_validated(validated_rows(meals))

    if summary["valid_count"] == 0:
        answer = (
            f"You logged {len(meals)} meal(s) {label}, but none of them "
            "passed nutrition validation, so I can't give a reliable total."
        )
    else:
        answer = (
            f"Based on {summary['valid_count']} validated meal(s) {label}, "
            f"your recorded intake is approximately "
            f"{summary['calories']:.0f} kcal, "
            f"{summary['protein_g']:.1f} g protein, "
            f"{summary['carbs_g']:.1f} g carbohydrates and "
            f"{summary['fat_g']:.1f} g fat."
        )

    if summary["flagged_count"]:
        answer += "\n\n" + flagged_note(summary["flagged_count"])

    answer += (
        "\n\nThese totals may be incomplete if you haven't logged "
        "everything you ate."
    )

    return {
        "answer": answer,
        "model": "sql",
        "meals_considered": len(meals),
    }


def answer_daily_budget(db: Session, user_id: UUID, message: str) -> dict:
    offset = extract_day_offset(message)
    label = day_label(offset)
    day = today_ist() - timedelta(days=offset)

    meals = query_meals(db, user_id, *day_bounds(day))
    spent = sum(float(meal.cost or 0) for meal in meals)

    profile = latest_profile(db, user_id)
    daily_budget = (
        float(profile.daily_budget)
        if profile is not None and profile.daily_budget is not None
        else None
    )

    if not meals:
        answer = f"You haven't logged any meals {label}, so nothing was spent."
    else:
        answer = (
            f"Across {len(meals)} logged meal(s) {label}, your recorded "
            f"spending is {spent:,.2f}."
        )

    if daily_budget is not None:
        difference = daily_budget - spent

        if difference >= 0:
            answer += (
                f" Your daily budget is {daily_budget:,.2f}, so "
                f"{difference:,.2f} was left."
            )
        else:
            answer += (
                f" Your daily budget is {daily_budget:,.2f}, so you were "
                f"{abs(difference):,.2f} over."
            )
    else:
        answer += " You haven't set a daily budget in your health profile."

    answer += (
        "\n\nThis includes only costs recorded against logged meals."
    )

    return {
        "answer": answer,
        "model": "sql",
        "meals_considered": len(meals),
    }


def answer_day_meals(db: Session, user_id: UUID, message: str) -> dict:
    offset = extract_day_offset(message)
    meal_type = extract_meal_type(message)
    today = today_ist()
    day = today - timedelta(days=offset)

    if wants_last_night(message):
        bounds = last_night_bounds(today)
        label = "last night (6 PM to 6 AM)"
        date_label = day.strftime("%d %b %Y")
        with_time = True
    else:
        bounds = day_bounds(day)
        label = day_label(offset)
        date_label = day.strftime("%d %b %Y")
        with_time = False

    meals = query_meals(db, user_id, *bounds, meal_type=meal_type)
    noun = meal_type or "meal"

    if not meals:
        answer = f"You haven't logged any {noun}s {label} ({date_label})."

        if meal_type:
            others = query_meals(db, user_id, *bounds)

            if others:
                answer += (
                    f" You did log {len(others)} other meal(s) in that "
                    "time. Ask for your meals to see them."
                )

        return {"answer": answer, "model": "sql", "meals_considered": 0}

    rows = validated_rows(meals)
    summary = summarize_validated(rows)

    answer = (
        f"You logged {len(meals)} {noun}(s) {label} ({date_label}):\n"
        + "\n".join(meal_line(row, with_time=with_time) for row in rows)
    )

    if summary["valid_count"]:
        answer += (
            f"\n\nTotals from the {summary['valid_count']} meal(s) that "
            f"passed nutrition validation: about "
            f"{summary['calories']:.0f} kcal and "
            f"{summary['protein_g']:.1f} g of protein."
        )

    if summary["flagged_count"]:
        answer += "\n\n" + flagged_note(summary["flagged_count"])

    answer += "\n\n" + INCOMPLETE_NOTE

    return {
        "answer": answer,
        "model": "sql",
        "meals_considered": len(meals),
    }


def answer_period_meals(db: Session, user_id: UUID, message: str) -> dict:
    first, day_after_last, label = resolve_date_range(message, today_ist())
    last_day = day_after_last - timedelta(days=1)
    span = (
        f"{first.strftime('%d %b')} to {last_day.strftime('%d %b %Y')}"
    )

    meals = query_meals(db, user_id, *range_bounds(first, day_after_last))

    if not meals:
        return {
            "answer": f"You haven't logged any meals {label} ({span}).",
            "model": "sql",
            "meals_considered": 0,
        }

    rows = validated_rows(meals)
    summary = summarize_validated(rows)

    days_with_logs = len({to_ist(m.consumed_at).date() for m in meals})
    days_in_range = (day_after_last - first).days

    answer = (
        f"You logged {len(meals)} meal(s) {label} ({span}), on "
        f"{days_with_logs} of {days_in_range} day(s)."
    )

    listed = rows[-MAX_LISTED_MEALS:]

    answer += "\n\n" + "\n".join(meal_line(row, with_date=True) for row in listed)

    if len(rows) > len(listed):
        answer += (
            f"\n(Showing the latest {len(listed)} of {len(rows)} meals.)"
        )

    if summary["valid_count"]:
        answer += (
            f"\n\nTotals from the {summary['valid_count']} meal(s) that "
            f"passed nutrition validation: about "
            f"{summary['calories']:.0f} kcal and "
            f"{summary['protein_g']:.1f} g of protein."
        )

    if summary["flagged_count"]:
        answer += "\n\n" + flagged_note(summary["flagged_count"])

    answer += "\n\n" + INCOMPLETE_NOTE

    return {
        "answer": answer,
        "model": "sql",
        "meals_considered": len(meals),
    }


HANDLERS = {
    "recent_meals": answer_recent_meals,
    "daily_nutrition": answer_daily_nutrition,
    "daily_budget": answer_daily_budget,
    "day_meals": answer_day_meals,
    "period_meals": answer_period_meals,
}
