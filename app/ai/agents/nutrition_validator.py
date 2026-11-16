
import math
from decimal import Decimal
from typing import Any


NUTRITION_FIELDS = (
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
)


def is_valid_nutrition_number(value: Any) -> bool:
    """Check whether a nutrition value is finite and non-negative."""

    if isinstance(value, bool):
        return False

    if not isinstance(value, (int, float, Decimal)):
        return False

    try:
        return math.isfinite(float(value)) and value >= 0
    except (TypeError, ValueError, OverflowError):
        return False


def validate_meal_nutrition(
    meal: dict[str, Any],
) -> list[str]:
    """Return nutrition quality warnings without modifying the meal."""

    if not isinstance(meal, dict):
        return ["Invalid meal record: expected an object."]

    warnings = []

    for field in NUTRITION_FIELDS:
        value = meal.get(field)

        if value is None:
            warnings.append(f"Missing nutrition value: {field}")

        elif not is_valid_nutrition_number(value):
            warnings.append(
                f"Invalid or negative nutrition value: {field}"
            )

    if warnings:
        return warnings

    calories = float(meal["calories"])
    protein = float(meal["protein_g"])
    carbs = float(meal["carbs_g"])
    fat = float(meal["fat_g"])

    estimated_calories = (
        protein * 4
        + carbs * 4
        + fat * 9
    )

    if not math.isfinite(estimated_calories):
        return ["Nutrition values are too large to validate safely."]

    if calories == 0 and estimated_calories > 0:
        warnings.append(
            "Recorded calories are zero despite "
            "non-zero macronutrients."
        )

    elif estimated_calories > 0:
        difference = abs(calories - estimated_calories)
        threshold = max(50, estimated_calories * 0.30)

        if difference > threshold:
            warnings.append(
                "Recorded calories differ significantly "
                "from calories estimated using macronutrients."
            )

    return warnings


def validate_meals(
    meals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach quality warnings while preserving original values."""

    if not isinstance(meals, list):
        raise TypeError("Expected meals to be a list.")

    validated_meals = []

    for meal in meals:
        if not isinstance(meal, dict):
            validated_meals.append({
                "data_quality_status": "flagged",
                "data_quality_warnings": [
                    "Invalid meal record: expected an object."
                ],
            })
            continue

        meal_copy = dict(meal)
        warnings = validate_meal_nutrition(meal_copy)

        meal_copy["data_quality_warnings"] = warnings
        meal_copy["data_quality_status"] = (
            "flagged" if warnings else "valid"
        )

        validated_meals.append(meal_copy)

    return validated_meals
