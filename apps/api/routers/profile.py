from fastapi import APIRouter, HTTPException, Response

from apps.api.auth.dependencies import CurrentUser, Db
from apps.api.models import FreelancerProfile
from apps.api.schemas.accounts import Profile, ProfileUpdate

router = APIRouter(tags=["profile"])


def owned_profile(user, db):
    profile = db.get(FreelancerProfile, user.id)
    if profile is None:
        raise HTTPException(404, "Profile not found")
    return profile


@router.get("/profile/me", response_model=Profile)
def get_profile(user: CurrentUser, db: Db, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return owned_profile(user, db)


@router.put("/profile/me", response_model=Profile)
def update_profile(body: ProfileUpdate, user: CurrentUser, db: Db, response: Response):
    profile = owned_profile(user, db)
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    profile.onboarding_complete = True
    db.commit()
    db.refresh(profile)
    response.headers["Cache-Control"] = "no-store"
    return profile
