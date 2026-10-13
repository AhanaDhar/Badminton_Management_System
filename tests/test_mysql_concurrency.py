"""MySQL-only tests for races that an in-memory database cannot model."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
import pytest
from backend.extensions import db
from .test_management import post, session_data


def concurrent_posts(app, path, headers, bodies):
    barrier = Barrier(len(bodies))

    def send(body):
        with app.test_client() as client:
            barrier.wait(timeout=10)
            response = client.post("/api/" + path, headers=headers, json=body)
            return response.status_code

    with ThreadPoolExecutor(max_workers=len(bodies)) as pool:
        return sorted(pool.map(send, bodies))


def require_mysql():
    if db.engine.dialect.name != "mysql":
        pytest.skip(
            "Requires TEST_DATABASE_URL pointing to a disposable MySQL database"
        )


def test_concurrent_bookings_cannot_overlap(app, client, academy):
    require_mysql()
    data = session_data(academy)
    booking = {k: data[k] for k in ("court_id", "starts_at", "ends_at")}
    booking["purpose"] = "Concurrent test"
    assert concurrent_posts(app, "bookings", academy["admin"], [booking, booking]) == [
        201,
        409,
    ]


def test_concurrent_payments_cannot_overpay(app, client, academy):
    require_mysql()
    fee = post(
        client,
        academy["admin"],
        "fees",
        {
            "student_id": academy["students"][0]["id"],
            "description": "Concurrent fee",
            "amount": "1000.00",
            "due_date": date.today().isoformat(),
        },
    )
    data = {
        "fee_id": fee["id"],
        "amount": "700.00",
        "paid_on": date.today().isoformat(),
        "method": "cash",
        "reference": "RACE-1",
    }
    assert concurrent_posts(
        app, "payments", academy["admin"], [data, dict(data, reference="RACE-2")]
    ) == [201, 409]
