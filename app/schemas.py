
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthProfileCreate(BaseModel):
    goals: str = Field(min_length=1, max_length=500)
    dietary_preferences: str = Field(
        min_length=1,
        max_length=500,
    )
    daily_budget: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
    )

    daily_calories_target: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    daily_protein_target_g: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    daily_carbs_target_g: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    daily_fat_target_g: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )


class HealthProfileResponse(HealthProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class MealLogCreate(BaseModel):
    food_name: str = Field(min_length=1, max_length=200)
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    portion: str = Field(min_length=1, max_length=100)

    calories: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    protein_g: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=10, decimal_places=2
    )
    carbs_g: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=10, decimal_places=2
    )
    fat_g: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=10, decimal_places=2
    )
    cost: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=10, decimal_places=2
    )


class MealLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_name: str
    meal_type: str
    portion: str
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    cost: Decimal
    consumed_at: datetime
    created_at: datetime

class MealLogUpdate(MealLogCreate):
    """Full meal update using the same validated fields as meal creation."""
    pass