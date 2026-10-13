from datetime import timedelta
from sqlalchemy import select
from backend.extensions import db
from backend.models import AuthSession, User, utcnow
from .conftest import auth, PASSWORD, NEW_PASSWORD


def test_login_logout_and_hash(client):
    header = auth(client)
    assert db.session.scalar(select(User)).password_hash != PASSWORD
    assert client.get("/api/auth/me", headers=header).json["role"] == "ADMIN"
    assert client.post("/api/auth/logout", headers=header).status_code == 200
    assert client.get("/api/auth/me", headers=header).status_code == 401


def test_wrong_role_password_and_rate_limit(client):
    data = {"login_id": "ADM001", "role": "COACH", "password": PASSWORD}
    assert client.post("/api/auth/login", json=data).status_code == 401
    data.update(role="ADMIN", password="wrong")
    for _ in range(4):
        assert client.post("/api/auth/login", json=data).status_code == 401
    assert client.post("/api/auth/login", json=data).status_code == 429


def test_missing_expired_and_deactivated_session(client):
    assert client.get("/api/auth/me").status_code == 401
    header = auth(client)
    session = db.session.scalar(select(AuthSession))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert client.get("/api/auth/me", headers=header).status_code == 401
    header = auth(client)
    db.session.scalar(select(User)).active = False
    db.session.commit()
    assert client.get("/api/auth/me", headers=header).status_code == 401


def test_password_change_revokes_all_sessions(client):
    first, second = auth(client), auth(client)
    assert (
        client.post(
            "/api/auth/password",
            headers=first,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me", headers=second).status_code == 401
    auth(client, password=NEW_PASSWORD)


def test_input_errors(client):
    assert client.post("/api/auth/login", json=[]).status_code == 400
    assert client.post("/api/auth/login", json={"role": "ROOT"}).status_code == 400
