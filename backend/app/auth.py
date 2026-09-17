from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_session
from app.models import RefreshToken, User

hashing = PasswordHash.recommended()
security = HTTPBearer()
def make_token(user_id: str, kind: str, lifetime: timedelta, token_id: str | None = None) -> str:
    claims = {"sub": user_id, "kind": kind, "exp": datetime.now(timezone.utc) + lifetime}
    if token_id:
        claims["jti"] = token_id
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
def token_pair(session: Session, user_id: str) -> tuple[str, str]:
    refresh_id = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    session.add(RefreshToken(user_id=user_id, token_id=refresh_id, expires_at=expires_at))
    session.commit()
    return make_token(user_id, "access", timedelta(minutes=30)), make_token(user_id, "refresh", timedelta(days=30), refresh_id)
def current_user(credentials: HTTPAuthorizationCredentials = Depends(security), session: Session = Depends(get_session)) -> User:
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as error:
        raise HTTPException(401, "Invalid token") from error
    if claims.get("kind") != "access" or not (user := session.get(User, claims.get("sub"))):
        raise HTTPException(401, "Invalid token")
    return user
