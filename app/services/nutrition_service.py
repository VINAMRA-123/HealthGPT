
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.ai.agents.nutrition_validator import validate_meals
from app.models import HealthProfile, MealLog


IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def to_float(value):
    """Convert Decimal or None into a JSON-friendly float."""
    return float(value or 0)


def get_latest_profile(db: Session, user_id: UUID):
    """Get the latest health profile belonging to this user."""
    return (
        db.query(HealthProfile)
        .filter(HealthProfile.user_id == user_id)
        .order_by(HealthProfile.id.desc())
        .first()
    )


def get_period_bounds(period_days: int):
    """
    Return UTC boundaries for the last N calendar days,
    including today, using the Asia/Kolkata timezone.
    """
    if not 1 <= period_days <= 365:
        raise ValueError("period_days must be between 1 and 365.")

    today = datetime.now(IST).date()
    start_date = today - timedelta(days=period_days - 1)
    end_date = today + timedelta(days=1)

    start_ist = datetime.combine(start_date, time.min, tzinfo=IST)
    end_ist = datetime.combine(end_date, time.min, tzinfo=IST)

    return (
        start_ist.astimezone(UTC),
        end_ist.astimezone(UTC),
    )


def get_period_totals(
    db: Session,
    user_id: UUID,
    period_days: int = 7,
):
    """Aggregate nutrition and spending for the requested period."""
    start_utc, end_utc = get_period_bounds(period_days)

    result = (
        db.query(
            func.coalesce(func.sum(MealLog.calories), 0),
            func.coalesce(func.sum(MealLog.protein_g), 0),
            func.coalesce(func.sum(MealLog.carbs_g), 0),
            func.coalesce(func.sum(MealLog.fat_g), 0),
            func.coalesce(func.sum(MealLog.cost), 0),
            func.count(MealLog.id),
        )
        .filter(
            MealLog.user_id == user_id,
            MealLog.consumed_at >= start_utc,
            MealLog.consumed_at < end_utc,
        )
        .one()
    )

    return {
        "period_days": period_days,
        "calories": to_float(result[0]),
        "protein_g": to_float(result[1]),
        "carbs_g": to_float(result[2]),
        "fat_g": to_float(result[3]),
        "total_cost": to_float(result[4]),
        "meal_count": result[5],
    }


def get_budget_summary(
    db: Session,
    user_id: UUID,
    period_days: int = 7,
):
    """Compare actual spending with the user's total period budget."""
    totals = get_period_totals(db, user_id, period_days)
    profile = get_latest_profile(db, user_id)

    daily_budget = (
        to_float(profile.daily_budget)
        if profile and profile.daily_budget is not None
        else None
    )

    if daily_budget is None:
        return {
            "period_days": period_days,
            "total_spent": totals["total_cost"],
            "daily_budget": None,
            "period_budget": None,
            "remaining_budget": None,
            "budget_used_percentage": None,
            "message": "No daily budget is configured in your health profile.",
        }

    period_budget = daily_budget * period_days
    remaining = period_budget - totals["total_cost"]

    percentage = (
        (totals["total_cost"] / period_budget) * 100
        if period_budget > 0
        else None
    )

    return {
        "period_days": period_days,
        "total_spent": totals["total_cost"],
        "daily_budget": daily_budget,
        "period_budget": round(period_budget, 2),
        "remaining_budget": round(remaining, 2),
        "budget_used_percentage": (
            round(percentage, 2) if percentage is not None else None
        ),
    }



def get_nutrition_summary(
    db: Session,
    user_id: UUID,
    period_days: int = 1,
):
    """Return validated nutrition totals and configured targets."""

    start_utc, end_utc = get_period_bounds(period_days)

    profile = get_latest_profile(db, user_id)

    # Retrieve every meal in the requested period.
    meal_records = (
        db.query(MealLog)
        .filter(
            MealLog.user_id == user_id,
            MealLog.consumed_at >= start_utc,
            MealLog.consumed_at < end_utc,
        )
        .order_by(MealLog.consumed_at.asc())
        .all()
    )

    # Convert ORM objects into dictionaries without replacing
    # missing nutrition values with zero.
    raw_meals = [
        {
            "id": meal.id,
            "food_name": meal.food_name,
            "calories": meal.calories,
            "protein_g": meal.protein_g,
            "carbs_g": meal.carbs_g,
            "fat_g": meal.fat_g,
        }
        for meal in meal_records
    ]

    # Reuse the same validator used by the AI agents.
    validated_meals = validate_meals(raw_meals)

    nutrition_fields = (
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
    )

    totals = {
        field: Decimal("0")
        for field in nutrition_fields
    }

    missing_or_invalid_counts = {
        field: 0
        for field in nutrition_fields
    }

    valid_meal_count = 0
    flagged_meal_count = 0

    for meal in validated_meals:

        if meal["data_quality_status"] == "flagged":
            flagged_meal_count += 1

            # Track which nutrition fields are missing or invalid.
            for warning in meal["data_quality_warnings"]:
                for field in nutrition_fields:
                    if (
                        warning.startswith(
                            f"Missing nutrition value: {field}"
                        )
                        or warning.startswith(
                            f"Invalid or negative nutrition value: {field}"
                        )
                    ):
                        missing_or_invalid_counts[field] += 1

            # Never include flagged nutrition in reliable totals.
            continue

        valid_meal_count += 1

        for field in nutrition_fields:
            totals[field] += Decimal(str(meal[field]))

    meal_count = len(validated_meals)

    if meal_count == 0:
        coverage_status = "no_data"
    elif flagged_meal_count > 0:
        coverage_status = "partial"
    else:
        coverage_status = "complete"

    nutrition_totals = {
        field: float(value)
        for field, value in totals.items()
    }

    result = {
        "period_days": period_days,
        **nutrition_totals,

        "meal_count": meal_count,
        "valid_meal_count": valid_meal_count,
        "flagged_meal_count": flagged_meal_count,

        "daily_average": {
            field: round(value / period_days, 2)
            for field, value in nutrition_totals.items()
        },

        "nutrition_data_quality": {
            "status": coverage_status,
            "totals_are_partial": flagged_meal_count > 0,
            "missing_or_invalid_counts": missing_or_invalid_counts,
            "excluded_meal_count": flagged_meal_count,
            "explanation": (
                "Nutrition totals include only meals that passed "
                "validation. Flagged meal values were excluded."
                if flagged_meal_count > 0
                else (
                    "No meals were logged during this period."
                    if meal_count == 0
                    else "All logged meals passed nutrition validation."
                )
            ),
        },

        "daily_targets": None,
    }

    if profile:
        result["daily_targets"] = {
            "calories": (
                float(profile.daily_calories_target)
                if profile.daily_calories_target is not None
                else None
            ),
            "protein_g": (
                float(profile.daily_protein_target_g)
                if profile.daily_protein_target_g is not None
                else None
            ),
            "carbs_g": (
                float(profile.daily_carbs_target_g)
                if profile.daily_carbs_target_g is not None
                else None
            ),
            "fat_g": (
                float(profile.daily_fat_target_g)
                if profile.daily_fat_target_g is not None
                else None
            ),
        }

    return result


def get_recent_meals(
    db: Session,
    user_id: UUID,
    limit: int = 5,
):
    """Return the most recent meals belonging to this user."""
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20.")

    meals = (
        db.query(MealLog)
        .filter(MealLog.user_id == user_id)
        .order_by(MealLog.consumed_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": meal.id,
            "food_name": meal.food_name,
            "meal_type": meal.meal_type,
            "portion": meal.portion,
            "calories": to_float(meal.calories),
            "protein_g": to_float(meal.protein_g),
            "carbs_g": to_float(meal.carbs_g),
            "fat_g": to_float(meal.fat_g),
            "cost": to_float(meal.cost),
            "consumed_at": (
                meal.consumed_at.isoformat()
                if meal.consumed_at
                else None
            ),
        }
        for meal in meals
    ]


def get_health_profile(db: Session, user_id: UUID):
    """Return the authenticated user's latest health profile."""
    profile = get_latest_profile(db, user_id)

    if not profile:
        return {
            "profile_exists": False,
            "message": "No health profile has been created yet.",
        }

    return {
        "profile_exists": True,
        "goals": profile.goals,
        "dietary_preferences": profile.dietary_preferences,
        "daily_budget": to_float(profile.daily_budget),
        "daily_targets": {
            "calories": to_float(profile.daily_calories_target),
            "protein_g": to_float(profile.daily_protein_target_g),
            "carbs_g": to_float(profile.daily_carbs_target_g),
            "fat_g": to_float(profile.daily_fat_target_g),
        },
    }
