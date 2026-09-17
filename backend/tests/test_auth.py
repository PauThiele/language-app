import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.auth import current_user
from app.config import Settings
from app.main import login, logout, refresh, register
from app.models import RefreshToken
from app.schemas import Credentials, RefreshRequest


def test_production_rejects_the_development_jwt_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET must be changed"):
        Settings(environment="production")


def test_runtime_rejects_incomplete_generation_provider_configuration() -> None:
    with pytest.raises(ValueError, match="must be set together"):
        Settings(generation_provider_url="https://provider.example/readings")
    with pytest.raises(ValueError, match="must be set together"):
        Settings(generation_provider_token="test-token")


def test_registration_login_refresh_and_logout_revoke_refresh_sessions() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            credentials = Credentials(email="reader@example.com", password="safe-password")
            registered = register(credentials, session)
            signed_in = login(credentials, session)

            assert registered.refresh_token != signed_in.refresh_token
            assert len(list(session.scalars(select(RefreshToken)))) == 2

            refreshed = refresh(RefreshRequest(refresh_token=registered.refresh_token), session)
            assert refreshed.refresh_token != registered.refresh_token
            from fastapi.security import HTTPAuthorizationCredentials
            assert current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=refreshed.access_token), session).email == credentials.email
            with pytest.raises(HTTPException, match="Invalid refresh token"):
                refresh(RefreshRequest(refresh_token=registered.refresh_token), session)

            logout(RefreshRequest(refresh_token=refreshed.refresh_token), session)
            with pytest.raises(HTTPException, match="Invalid refresh token"):
                refresh(RefreshRequest(refresh_token=refreshed.refresh_token), session)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
