
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.db import get_db
from app.models import HealthProfile
from app.schemas import HealthProfileCreate, HealthProfileResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/health/profile",
    tags=["Health"],
)


@router.get("/me", response_model=HealthProfileResponse)
def get_my_health_profile(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(HealthProfile)
        .filter(HealthProfile.user_id == user_id)
        .order_by(HealthProfile.id.desc())
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Health profile not found. Create your profile first.",
        )

    return profile


@router.put("/me", response_model=HealthProfileResponse)
def upsert_my_health_profile(
    profile_data: HealthProfileCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    print("PROFILE PAYLOAD:", profile_data.model_dump())
    try:
        profile = (
            db.query(HealthProfile)
            .filter(HealthProfile.user_id == user_id)
            .order_by(HealthProfile.id.desc())
            .first()
        )

        if profile is None:
            profile = HealthProfile(
                user_id=user_id,
                **profile_data.model_dump(),
            )
            db.add(profile)
        else:
            for field, value in profile_data.model_dump(
                exclude_unset=True
            ).items():
                setattr(profile, field, value)


        db.commit()
        db.refresh(profile)

        print("SAVED PROFILE ID:", profile.id)
        print("SAVED TARGETS:", {
            "calories": profile.daily_calories_target,
            "protein": profile.daily_protein_target_g,
            "carbs": profile.daily_carbs_target_g,
            "fat": profile.daily_fat_target_g,
        })

        return profile


    except Exception:
        db.rollback()
        logger.exception("Failed to save health profile")
        raise


@router.post(
    "",
    response_model=HealthProfileResponse,
    status_code=201,
)
def create_health_profile(
    profile_data: HealthProfileCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    new_profile = HealthProfile(
        user_id=user_id,
        **profile_data.model_dump(),
    )

    try:
        db.add(new_profile)
        db.commit()
        db.refresh(new_profile)
        return new_profile
    except Exception:
        db.rollback()
        logger.exception("Failed to create health profile")
        raise


@router.get("/{profile_id}", response_model=HealthProfileResponse)
def get_health_profile(
    profile_id: int,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(HealthProfile)
        .filter(
            HealthProfile.id == profile_id,
            HealthProfile.user_id == user_id,
        )
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Health profile not found",
        )

    return profile
