from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select
from backend.extensions import db
from backend.models import Attendance, CourtBooking, Enrollment, Fee, utcnow
from backend.services.seed import seed
from backend.utils.time import academy_today
from .conftest import auth, PASSWORD
from .test_management import post, session_data


def test_monthly_report_uses_payment_dates_and_exports_safe_csv(client, academy):
    student = academy["students"][0]
    admin = academy["admin"]
    month = academy_today().replace(day=1)
    fee = post(
        client,
        admin,
        "fees",
        {
            "student_id": student["id"],
            "description": "Training",
            "amount": "1000.00",
            "due_date": month.isoformat(),
        },
    )
    db.session.get(Fee, fee["id"]).created_on = month
    db.session.commit()
    post(
        client,
        admin,
        "payments",
        {
            "fee_id": fee["id"],
            "amount": "250.00",
            "paid_on": academy_today().isoformat(),
            "method": "cash",
            "reference": "REPORT-1",
        },
    )
    client.patch(
        f"/api/students/{student['id']}", headers=admin, json={"name": "=DANGEROUS()"}
    )
    response = client.get(
        "/api/reports/monthly",
        headers=admin,
        query_string={"month": month.strftime("%Y-%m")},
    )
    assert response.json["collected"] == "250.00"
    assert response.json["outstanding"] == "750.00"
    csv = client.get(
        "/api/reports/monthly",
        headers=admin,
        query_string={"month": month.strftime("%Y-%m"), "format": "csv"},
    )
    assert b"'=DANGEROUS()" in csv.data
    previous = (month - timedelta(days=1)).strftime("%Y-%m")
    earlier = client.get(
        "/api/reports/monthly", headers=admin, query_string={"month": previous}
    ).json
    assert earlier["collected"] == "0.00" and earlier["outstanding"] == "0.00"


def test_attendance_denominator_includes_unmarked_and_excludes_excused(client, academy):
    record = post(client, academy["admin"], "sessions", session_data(academy))
    booking = db.session.get(CourtBooking, record["booking_id"])
    booking.starts_at = utcnow() - timedelta(hours=2)
    booking.ends_at = utcnow() - timedelta(hours=1)
    db.session.commit()
    data = client.get("/api/analytics", headers=academy["student"]).json
    assert data["attendance_percentage"] == 0 and data["unmarked_attendance"] == 1
    enrollment = db.session.scalar(
        select(Enrollment).where(Enrollment.session_id == record["id"])
    )
    db.session.add(
        Attendance(enrollment_id=enrollment.id, status="excused", marked_by=1)
    )
    db.session.commit()
    assert (
        client.get("/api/analytics", headers=academy["student"]).json[
            "attendance_percentage"
        ]
        is None
    )


def test_seed_empty_database_only(app, client):
    from sqlalchemy import delete
    from backend.models import User, PerformanceRecord

    db.session.execute(delete(User))
    db.session.commit()
    seed(PASSWORD)
    headers = auth(client)
    data = client.get("/api/analytics", headers=headers).json
    assert data["students"] == 6 and data["coaches"] == 2
    assert data["achievements"] == 2
    assert len(list(db.session.scalars(select(PerformanceRecord)))) == 48
    assert Decimal(data["outstanding"]) > 0
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed-demo", "--password", PASSWORD])
    assert result.exit_code != 0
    assert client.get("/api/analytics", headers=headers).json["students"] == 6
