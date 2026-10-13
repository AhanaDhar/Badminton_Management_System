import os
import secrets
import pytest
from werkzeug.security import generate_password_hash
from backend import create_app
from backend.extensions import db
from backend.models import Court, User

PASSWORD = secrets.token_urlsafe(24)
NEW_PASSWORD = secrets.token_urlsafe(24)


@pytest.fixture
def app():
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": os.getenv("TEST_DATABASE_URL", "sqlite://"),
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        }
    )
    with application.app_context():
        db.create_all()
        db.session.add(
            User(
                login_id="ADM001",
                name="Test Admin",
                email="admin@example.com",
                role="ADMIN",
                password_hash=generate_password_hash(PASSWORD),
            )
        )
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def auth(client, login_id="ADM001", role="ADMIN", password=PASSWORD):
    result = client.post(
        "/api/auth/login",
        json={"role": role, "login_id": login_id, "password": password},
    )
    assert result.status_code == 200, result.json
    return {"Authorization": "Bearer " + result.json["token"]}


@pytest.fixture
def academy(client):
    from .test_management import post

    admin = auth(client)
    coaches = [
        post(
            client,
            admin,
            "coaches",
            {
                "login_id": f"C{i}",
                "name": f"Coach {i}",
                "email": f"c{i}@example.com",
                "password": PASSWORD,
                "specialty": "Singles",
            },
        )
        for i in (1, 2)
    ]
    students = [
        post(
            client,
            admin,
            "students",
            {
                "login_id": f"S{i}",
                "name": f"Student {i}",
                "email": f"s{i}@example.com",
                "password": PASSWORD,
                "date_of_birth": "2010-01-01",
                "joined_on": "2024-01-01",
                "level": "Beginner",
                "coach_id": coaches[i - 1]["id"],
            },
        )
        for i in (1, 2)
    ]
    db.session.add_all([Court(name="Court 1"), Court(name="Court 2")])
    db.session.commit()
    return {
        "admin": admin,
        "coach": auth(client, "C1", "COACH"),
        "coach2": auth(client, "C2", "COACH"),
        "student": auth(client, "S1", "STUDENT"),
        "coaches": coaches,
        "students": students,
    }
