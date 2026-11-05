import hmac
from datetime import UTC
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from apps.api.auth.security import csrf_for, token_digest
from apps.api.database import get_db
from apps.api.models import User, UserSession, utcnow

Db = Annotated[Session, Depends(get_db)]


def require_origin(request: Request):
    origin = request.headers.get("origin")
    if origin is not None and origin != request.app.state.settings.web_origin:
        raise HTTPException(403, "Untrusted request origin")


def require_user(request: Request, db: Db) -> User:
    token = request.cookies.get(request.app.state.settings.session_cookie_name, "")
    if not token:
        raise HTTPException(401, "Sign in required")
    session = db.get(UserSession, token_digest(token))
    if session is None:
        raise HTTPException(401, "Invalid or expired session")
    expiry = session.expires_at
    if expiry.tzinfo is None:  # SQLite's test driver returns naive datetimes.
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= utcnow():
        db.delete(session)
        db.commit()
        raise HTTPException(401, "Invalid or expired session")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_for(token)):
            raise HTTPException(403, "Missing or invalid CSRF token")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "Invalid or expired session")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
