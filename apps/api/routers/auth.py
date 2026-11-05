from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from apps.api.auth.dependencies import CurrentUser, Db, require_origin
from apps.api.auth.security import DUMMY_HASH, PASSWORDS, csrf_for, new_session_token, token_digest
from apps.api.models import FreelancerProfile, User, UserSession, utcnow
from apps.api.schemas.accounts import Account, Credentials

router = APIRouter(tags=["auth"])


def issue_session(user: User, request: Request, response: Response, db) -> Account:
    settings = request.app.state.settings
    token = new_session_token()
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.expires_at <= utcnow(),
        )
    )
    db.add(
        UserSession(
            token_digest=token_digest(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=settings.session_lifetime_hours),
        )
    )
    db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_lifetime_hours * 3600,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return Account(id=user.id, email=user.email, csrf_token=csrf_for(token))


def limit_attempt(request: Request):
    key = request.client.host if request.client else "unknown"
    if not request.app.state.auth_limiter.allow(key):
        raise HTTPException(429, "Too many account requests; try again later")


@router.post(
    "/auth/register",
    response_model=Account,
    status_code=201,
    dependencies=[Depends(require_origin), Depends(limit_attempt)],
)
def register(body: Credentials, request: Request, response: Response, db: Db):
    user = User(email=str(body.email), password_hash=PASSWORDS.hash(body.password))
    db.add(user)
    try:
        db.flush()
        db.add(FreelancerProfile(user_id=user.id))
        db.flush()
        return issue_session(user, request, response, db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists") from None


@router.post(
    "/auth/login",
    response_model=Account,
    dependencies=[Depends(require_origin), Depends(limit_attempt)],
)
def login(body: Credentials, request: Request, response: Response, db: Db):
    user = db.scalar(select(User).where(User.email == str(body.email)))
    valid = PASSWORDS.verify(body.password, user.password_hash if user else DUMMY_HASH)
    if not valid or user is None:
        raise HTTPException(401, "Invalid email or password")
    previous = request.cookies.get(request.app.state.settings.session_cookie_name)
    if previous:
        db.execute(delete(UserSession).where(UserSession.token_digest == token_digest(previous)))
    return issue_session(user, request, response, db)


@router.get("/auth/me", response_model=Account)
def me(user: CurrentUser, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    token = request.cookies[request.app.state.settings.session_cookie_name]
    return Account(id=user.id, email=user.email, csrf_token=csrf_for(token))


@router.post("/auth/logout", status_code=204)
def logout(user: CurrentUser, request: Request, response: Response, db: Db):
    settings = request.app.state.settings
    token = request.cookies[settings.session_cookie_name]
    db.execute(delete(UserSession).where(UserSession.token_digest == token_digest(token)))
    db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
