
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


from app.auth import get_current_user_id
from app.db import get_db
from app.models import MealLog,HealthProfile
from app.schemas import MealLogCreate, MealLogResponse, MealLogUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/meals",
    tags=["Meals"],
)

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


@router.post("", response_model=MealLogResponse, status_code=201)
def create_meal(
    meal_data: MealLogCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    meal = MealLog(
        user_id=user_id,
        **meal_data.model_dump(),
    )

    try:
        db.add(meal)
        db.commit()
        db.refresh(meal)
        return meal
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to save meal")
        raise HTTPException(
            status_code=500,
            detail="Could not save meal. Please try again.",
        ) from exc


@router.get("", response_model=list[MealLogResponse])
def get_my_meals(
    limit: int = Query(default=50, ge=1, le=100),
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(MealLog)
        .filter(MealLog.user_id == user_id)
        .order_by(MealLog.consumed_at.desc())
        .limit(limit)
        .all()
    )



@router.get("/daily-summary")
def get_daily_summary(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    now_ist = datetime.now(IST)

    start_ist = datetime.combine(
        now_ist.date(),
        time.min,
        tzinfo=IST,
    )
    end_ist = start_ist + timedelta(days=1)

    start_utc = start_ist.astimezone(UTC)
    end_utc = end_ist.astimezone(UTC)

    # Calculate today's nutrition and cost.
    totals = (
        db.query(
            func.coalesce(
                func.sum(MealLog.calories), 0
            ).label("calories"),
            func.coalesce(
                func.sum(MealLog.protein_g), 0
            ).label("protein_g"),
            func.coalesce(
                func.sum(MealLog.carbs_g), 0
            ).label("carbs_g"),
            func.coalesce(
                func.sum(MealLog.fat_g), 0
            ).label("fat_g"),
            func.coalesce(
                func.sum(MealLog.cost), 0
            ).label("cost"),
            func.count(MealLog.id).label("meal_count"),
        )
        .filter(
            MealLog.user_id == user_id,
            MealLog.consumed_at >= start_utc,
            MealLog.consumed_at < end_utc,
        )
        .one()
    )

    consumed = {
        "calories": Decimal(str(totals.calories)),
        "protein_g": Decimal(str(totals.protein_g)),
        "carbs_g": Decimal(str(totals.carbs_g)),
        "fat_g": Decimal(str(totals.fat_g)),
    }

    # Load this authenticated user's latest health profile.
    profile = (
        db.query(HealthProfile)
        .filter(HealthProfile.user_id == user_id)
        .order_by(HealthProfile.id.desc())
        .first()
    )

    targets = {
        "calories": (
            profile.daily_calories_target
            if profile else None
        ),
        "protein_g": (
            profile.daily_protein_target_g
            if profile else None
        ),
        "carbs_g": (
            profile.daily_carbs_target_g
            if profile else None
        ),
        "fat_g": (
            profile.daily_fat_target_g
            if profile else None
        ),
    }

    remaining = {}
    progress_percent = {}

    for nutrient, consumed_value in consumed.items():
        target = targets[nutrient]

        if target is None or target <= 0:
            remaining[nutrient] = None
            progress_percent[nutrient] = None
        else:
            remaining[nutrient] = max(
                target - consumed_value,
                Decimal("0"),
            )

            progress_percent[nutrient] = (
                consumed_value * Decimal("100") / target
            ).quantize(Decimal("0.01"))


    return {
        "date": now_ist.date().isoformat(),
        "timezone": "Asia/Kolkata",
        "meal_count": totals.meal_count,
        "calories": consumed["calories"],
        "protein_g": consumed["protein_g"],
        "carbs_g": consumed["carbs_g"],
        "fat_g": consumed["fat_g"],
        "cost": Decimal(str(totals.cost)),
        "consumed": consumed,
        "targets": targets,
        "remaining": remaining,
        "progress_percent": progress_percent,
    }


@router.get("/weekly-summary")
def get_weekly_summary(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    now_ist = datetime.now(IST)
    today = now_ist.date()

    # Seven calendar days, including today.
    start_date = today - timedelta(days=6)

    start_ist = datetime.combine(
        start_date,
        time.min,
        tzinfo=IST,
    )
    end_ist = datetime.combine(
        today + timedelta(days=1),
        time.min,
        tzinfo=IST,
    )

    start_utc = start_ist.astimezone(UTC)
    end_utc = end_ist.astimezone(UTC)

    # Convert consumed_at to Indian local time before grouping.
    local_meal_date = func.date(
        func.timezone("Asia/Kolkata", MealLog.consumed_at)
    )

    rows = (
        db.query(
            local_meal_date.label("meal_date"),
            func.coalesce(
                func.sum(MealLog.calories), 0
            ).label("calories"),
            func.coalesce(
                func.sum(MealLog.protein_g), 0
            ).label("protein_g"),
            func.coalesce(
                func.sum(MealLog.carbs_g), 0
            ).label("carbs_g"),
            func.coalesce(
                func.sum(MealLog.fat_g), 0
            ).label("fat_g"),
            func.coalesce(
                func.sum(MealLog.cost), 0
            ).label("cost"),
            func.count(MealLog.id).label("meal_count"),
        )
        .filter(
            MealLog.user_id == user_id,
            MealLog.consumed_at >= start_utc,
            MealLog.consumed_at < end_utc,
        )
        .group_by(local_meal_date)
        .all()
    )

    # Map database results by date.
    daily_totals = {
        row.meal_date.isoformat(): row
        for row in rows
    }

    # Get the authenticated user's daily calorie target.
    profile = (
        db.query(HealthProfile)
        .filter(HealthProfile.user_id == user_id)
        .order_by(HealthProfile.id.desc())
        .first()
    )

    calorie_target = (
        profile.daily_calories_target
        if profile else None
    )

    days = []

    for offset in range(7):
        current_date = start_date + timedelta(days=offset)
        date_key = current_date.isoformat()
        row = daily_totals.get(date_key)

        calories = (
            Decimal(str(row.calories))
            if row else Decimal("0")
        )
        protein_g = (
            Decimal(str(row.protein_g))
            if row else Decimal("0")
        )
        carbs_g = (
            Decimal(str(row.carbs_g))
            if row else Decimal("0")
        )
        fat_g = (
            Decimal(str(row.fat_g))
            if row else Decimal("0")
        )
        cost = (
            Decimal(str(row.cost))
            if row else Decimal("0")
        )

        progress_percent = None

        if calorie_target is not None and calorie_target > 0:
            progress_percent = (
                calories * Decimal("100") / calorie_target
            ).quantize(Decimal("0.01"))

        days.append({
            "date": date_key,
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "cost": cost,
            "meal_count": row.meal_count if row else 0,
            "calorie_target": calorie_target,
            "calorie_progress_percent": progress_percent,
        })

    return {
        "timezone": "Asia/Kolkata",
        "days": days,
    }


@router.put("/{meal_id}", response_model=MealLogResponse)
def update_meal(
    meal_id: int,
    meal_data: MealLogUpdate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    meal = (
        db.query(MealLog)
        .filter(
            MealLog.id == meal_id,
            MealLog.user_id == user_id,
        )
        .first()
    )

    if meal is None:
        raise HTTPException(
            status_code=404,
            detail="Meal not found.",
        )

    try:
        for field, value in meal_data.model_dump().items():
            setattr(meal, field, value)

        db.commit()
        db.refresh(meal)
        return meal

    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to update meal")
        raise HTTPException(
            status_code=500,
            detail="Could not update meal. Please try again.",
        ) from exc


@router.delete("/{meal_id}", status_code=204)
def delete_meal(
    meal_id: int,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    meal = (
        db.query(MealLog)
        .filter(
            MealLog.id == meal_id,
            MealLog.user_id == user_id,
        )
        .first()
    )

    if meal is None:
        raise HTTPException(
            status_code=404,
            detail="Meal not found.",
        )

    try:
        db.delete(meal)
        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to delete meal")
        raise HTTPException(
            status_code=500,
            detail="Could not delete meal. Please try again.",
        ) from exc