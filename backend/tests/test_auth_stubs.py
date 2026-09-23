import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.deps import get_current_user
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.database import Base
from app.users.models import User


def test_password_hashing() -> None:
    raw = "monMotDePasseSecret123"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("mauvaisMotDePasse", hashed) is False


def test_jwt_lifecycle() -> None:
    token = create_access_token(user_id=42)
    assert isinstance(token, str)

    user_id = decode_access_token(token)
    assert user_id == 42


def test_jwt_tampered_raises() -> None:
    token = create_access_token(user_id=42)
    tampered_token = token + "corrupted"

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered_token)


def test_get_current_user_missing_header() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    try:
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization=None, db=session)
        assert exc_info.value.status_code == 401
    finally:
        session.close()


def test_get_current_user_valid_token() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    try:
        user = User(username="alice", password_hash=hash_password("secret"))
        session.add(user)
        session.commit()
        session.refresh(user)

        token = create_access_token(user_id=user.id)
        current = get_current_user(authorization=f"Bearer {token}", db=session)
        assert current.id == user.id
        assert current.username == "alice"
    finally:
        session.close()
