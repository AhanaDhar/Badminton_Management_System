"""Execute real Streamlit scripts against the real Flask test client."""

from pathlib import Path
from urllib.parse import urlsplit
import pytest
import requests
from sqlalchemy import delete
from streamlit.testing.v1 import AppTest
from backend.extensions import db
from backend.models import User
from backend.services.seed import seed
from .conftest import PASSWORD

APP_PATH = Path(__file__).parents[1] / "frontend" / "app.py"


@pytest.fixture
def demo_api(app, monkeypatch):
    db.session.execute(delete(User))
    db.session.commit()
    seed(PASSWORD)

    def request(method, url, json=None, params=None, headers=None, timeout=None):
        with app.test_client() as client:
            result = client.open(
                urlsplit(url).path,
                method=method,
                json=json,
                query_string=params,
                headers=headers,
            )
        response = requests.Response()
        response.status_code = result.status_code
        response._content = result.data
        response.headers.update(result.headers)
        return response

    monkeypatch.setattr(requests, "request", request)
    return app.test_client()


def signed_app(client, login_id, role):
    response = client.post(
        "/api/auth/login",
        json={"role": role, "login_id": login_id, "password": PASSWORD},
    )
    assert response.status_code == 200
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.session_state["auth"] = response.json
    return at.run()


@pytest.mark.parametrize(
    "login_id,role", [("ADM001", "ADMIN"), ("C001", "COACH"), ("S001", "STUDENT")]
)
def test_all_role_pages_render(demo_api, login_id, role):
    at = signed_app(demo_api, login_id, role)
    assert not at.exception
    for page in at.radio(key="navigation").options:
        at.radio(key="navigation").set_value(page).run()
        assert not at.exception, f"{role} / {page}: {at.exception}"
        assert not at.error, f"{role} / {page}: {at.error}"


def test_login_and_logout(demo_api):
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    assert not at.exception
    at.text_input[0].set_value("S001")
    at.text_input[1].set_value(PASSWORD)
    at.button[0].click().run()
    assert not at.exception and not at.error
    assert at.radio(key="navigation").value == "Overview"
    next(b for b in at.button if b.label == "Sign out").click().run()
    assert not at.exception
    assert at.text_input[0].label == "Academy ID"


def test_admin_creates_and_edits_coach_through_ui(demo_api):
    at = signed_app(demo_api, "ADM001", "ADMIN")
    at.radio(key="navigation").set_value("Coaches").run()
    for label, value in [
        ("Academy ID", "C003"),
        ("Full name", "New Coach"),
        ("Email", "newcoach@example.com"),
        ("Password (12–128 characters)", PASSWORD),
        ("Specialty", "Defense"),
    ]:
        next(w for w in at.text_input if w.label == label).set_value(value)
    next(b for b in at.button if b.label == "Save coach").click().run()
    assert not at.exception and not at.error
    assert any("Changes saved" in item.value for item in at.success)
    db.session.remove()  # End the main-thread MySQL snapshot after a UI-thread write.
    response = demo_api.post(
        "/api/auth/login",
        json={"role": "COACH", "login_id": "C003", "password": PASSWORD},
    )
    assert response.status_code == 200

    at.radio(key="coaches_mode").set_value("Edit").run()
    at.selectbox(key="coaches_record").set_value(
        response.json["user"]["coach_id"]
    ).run()
    next(w for w in at.text_input if w.label == "Specialty").set_value(
        "Advanced defense"
    )
    next(b for b in at.button if b.label == "Save coach").click().run()
    assert not at.exception and not at.error
    header = {"Authorization": "Bearer " + response.json["token"]}
    db.session.remove()
    assert (
        demo_api.get("/api/coaches", headers=header).json[0]["specialty"]
        == "Advanced defense"
    )
