import hashlib
from functools import wraps
from flask import g, request
from sqlalchemy import select
from ..extensions import db
from ..models import AuthSession, utcnow
from .validation import APIError


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def require(*roles):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or len(header) > 200:
                raise APIError("Authentication required", 401)
            session = db.session.scalar(
                select(AuthSession).where(AuthSession.token_hash == digest(header[7:]))
            )
            if not session or session.expires_at <= utcnow() or not session.user.active:
                raise APIError("Session expired or invalid", 401)
            g.user, g.auth_session = session.user, session
            if roles and g.user.role not in roles:
                raise APIError("This role cannot perform this action", 403)
            return func(*args, **kwargs)

        return wrapped

    return decorator
