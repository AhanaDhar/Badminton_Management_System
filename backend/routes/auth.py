import secrets
from datetime import timedelta
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import delete, func, select
from werkzeug.security import check_password_hash, generate_password_hash
from ..extensions import db
from ..models import AuthSession, LoginAttempt, User, utcnow
from ..utils.security import digest, require
from ..utils.validation import APIError, choice, password, payload, text

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
# Equal-cost verification for unknown IDs; never disclose whether an account exists.
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32))


def identity(user):
    return {
        "id": user.id,
        "login_id": user.login_id,
        "role": user.role,
        "name": user.name,
        "student_id": user.student.id if user.student else None,
        "coach_id": user.coach.id if user.coach else None,
    }


@bp.post("/login")
def login():
    data = payload(("role", "login_id", "password"), ("role", "login_id", "password"))
    role = choice(data["role"], "role", ("ADMIN", "COACH", "STUDENT"))
    login_id = text(data["login_id"], "login_id", 40).upper()
    supplied = data["password"]
    if not isinstance(supplied, str) or not 1 <= len(supplied) <= 128:
        raise APIError("Invalid credentials", 401)
    now = utcnow()
    # Independent account and source limits; trust request.remote_addr, not untrusted headers.
    keys = (
        digest("account:" + login_id),
        digest("source:" + (request.remote_addr or "unknown")),
    )
    cutoff = now - timedelta(minutes=15)
    for key, limit in zip(keys, (5, 30)):
        count = db.session.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.key_hash == key, LoginAttempt.attempted_at > cutoff)
        )
        if count >= limit:
            raise APIError("Too many failed attempts. Try again in 15 minutes", 429)
    user = db.session.scalar(select(User).where(User.login_id == login_id))
    valid = check_password_hash(user.password_hash if user else DUMMY_HASH, supplied)
    if not user or not valid or user.role != role or not user.active:
        db.session.add_all([LoginAttempt(key_hash=key) for key in keys])
        db.session.commit()
        raise APIError("Invalid credentials", 401)
    token = secrets.token_urlsafe(48)
    expires = now + timedelta(hours=current_app.config["SESSION_HOURS"])
    db.session.add(
        AuthSession(token_hash=digest(token), user_id=user.id, expires_at=expires)
    )
    db.session.commit()
    return jsonify(
        token=token, expires_at=expires.isoformat() + "Z", user=identity(user)
    )


@bp.get("/me")
@require()
def me():
    return jsonify(identity(g.user))


@bp.post("/logout")
@require()
def logout():
    db.session.delete(g.auth_session)
    db.session.commit()
    return jsonify(message="Logged out")


@bp.post("/password")
@require()
def change_password():
    data = payload(
        ("current_password", "new_password"), ("current_password", "new_password")
    )
    if not isinstance(data["current_password"], str) or not check_password_hash(
        g.user.password_hash, data["current_password"]
    ):
        raise APIError("Current password is incorrect", 400)
    g.user.password_hash = generate_password_hash(password(data["new_password"]))
    db.session.execute(delete(AuthSession).where(AuthSession.user_id == g.user.id))
    db.session.commit()
    return jsonify(message="Password changed; all sessions revoked. Sign in again.")
