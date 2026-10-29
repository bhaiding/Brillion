import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

settings = get_settings()
serializer = URLSafeTimedSerializer(settings.session_signing_secret, salt="brillion-session-v1")


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def secret_hash(secret: str) -> str:
    return hmac.new(settings.session_signing_secret.encode(), secret.encode(), hashlib.sha256).hexdigest()


def verify_secret(secret: str, expected: str) -> bool:
    return hmac.compare_digest(secret_hash(secret), expected)


def issue_token(subject_id: uuid.UUID, room_id: uuid.UUID, role: str) -> str:
    return serializer.dumps({"sub": str(subject_id), "room": str(room_id), "role": role})


@dataclass(frozen=True)
class SessionClaims:
    subject_id: uuid.UUID
    room_id: uuid.UUID
    role: str


def read_token(token: str, max_age_seconds: int = 60 * 60 * 48) -> SessionClaims | None:
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
        return SessionClaims(
            subject_id=uuid.UUID(data["sub"]),
            room_id=uuid.UUID(data["room"]),
            role=str(data["role"]),
        )
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None


def admin_authorized(secret: str | None) -> bool:
    return bool(secret) and hmac.compare_digest(secret, settings.admin_secret)
