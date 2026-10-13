from datetime import date, timedelta
from backend.extensions import db
from backend.models import CourtBooking, utcnow


def post(client, headers, path, data, status=201):
    response = client.post("/api/" + path, headers=headers, json=data)
    assert response.status_code == status, response.json
    return response.json


def session_data(academy, court_id=1):
    start = utcnow() + timedelta(days=1)
    return {
        "coach_id": academy["coaches"][0]["id"],
        "court_id": court_id,
        "starts_at": start.isoformat() + "Z",
        "ends_at": (start + timedelta(hours=1)).isoformat() + "Z",
        "title": "Footwork",
        "focus": "Split step",
        "student_ids": [academy["students"][0]["id"]],
    }


def test_people_crud_and_authorization(client, academy):
    sid = academy["students"][0]["id"]
    assert len(client.get("/api/students", headers=academy["coach"]).json) == 1
    assert len(client.get("/api/students", headers=academy["student"]).json) == 1
    assert (
        client.get(
            f"/api/students/{academy['students'][1]['id']}", headers=academy["student"]
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/students/{sid}", headers=academy["coach"], json={"level": "Advanced"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/students/{sid}", headers=academy["admin"], json={"level": "Advanced"}
        ).json["level"]
        == "Advanced"
    )
    assert (
        client.patch(
            f"/api/students/{sid}", headers=academy["admin"], json={"role": "ADMIN"}
        ).status_code
        == 400
    )
    assert (
        client.delete(
            f"/api/coaches/{academy['coaches'][0]['id']}", headers=academy["admin"]
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/api/students/{sid}", headers=academy["admin"]).status_code
        == 204
    )
    assert client.get("/api/auth/me", headers=academy["student"]).status_code == 401
    assert (
        client.delete(
            f"/api/coaches/{academy['coaches'][0]['id']}", headers=academy["admin"]
        ).status_code
        == 204
    )


def test_assignment_and_deactivation(client, academy):
    sid, cid = academy["students"][0]["id"], academy["coaches"][0]["id"]
    assert (
        client.patch(
            f"/api/coaches/{cid}", headers=academy["admin"], json={"active": False}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/students/{sid}",
            headers=academy["admin"],
            json={"coach_id": academy["coaches"][1]["id"]},
        ).status_code
        == 200
    )
    assert client.get("/api/students", headers=academy["coach"]).json == []
    assert (
        client.patch(
            f"/api/coaches/{cid}", headers=academy["admin"], json={"active": False}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me", headers=academy["coach"]).status_code == 401
    assert (
        client.patch(
            f"/api/students/{sid}", headers=academy["admin"], json={"coach_id": cid}
        ).status_code
        == 400
    )


def test_schedule_conflicts_and_crud(client, academy):
    data = session_data(academy)
    record = post(client, academy["coach"], "sessions", data)
    assert (
        client.post("/api/sessions", headers=academy["coach"], json=data).status_code
        == 409
    )
    data["court_id"] = 2
    assert (
        client.post("/api/sessions", headers=academy["coach"], json=data).status_code
        == 409
    )
    assert len(client.get("/api/sessions", headers=academy["student"]).json) == 1
    assert (
        "student_ids"
        not in client.get("/api/sessions", headers=academy["student"]).json[0]
    )
    assert client.get("/api/sessions", headers=academy["coach2"]).json == []
    assert (
        client.patch(
            f"/api/sessions/{record['id']}",
            headers=academy["coach2"],
            json={"title": "Forged"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/sessions/{record['id']}",
            headers=academy["coach"],
            json={"title": "New title"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/bookings/{record['booking_id']}",
            headers=academy["admin"],
            json={"purpose": "Bypass"},
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/sessions/{record['id']}", headers=academy["coach"]
        ).status_code
        == 204
    )
    assert db.session.get(CourtBooking, record["booking_id"]) is None


def test_booking_overlap_and_boundary(client, academy):
    data = session_data(academy)
    data = {k: data[k] for k in ("court_id", "starts_at", "ends_at")}
    data["purpose"] = "Private practice"
    first = post(client, academy["admin"], "bookings", data)
    assert (
        client.post("/api/bookings", headers=academy["admin"], json=data).status_code
        == 409
    )
    adjacent = dict(
        data,
        starts_at=data["ends_at"],
        ends_at=(utcnow() + timedelta(days=1, hours=2)).isoformat() + "Z",
    )
    post(client, academy["admin"], "bookings", adjacent)
    assert (
        client.post("/api/bookings", headers=academy["student"], json=data).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/bookings/{first['id']}", headers=academy["admin"]
        ).status_code
        == 204
    )


def test_attendance_upsert_and_history_protection(client, academy):
    record = post(client, academy["coach"], "sessions", session_data(academy))
    data = {
        "session_id": record["id"],
        "student_id": academy["students"][0]["id"],
        "status": "present",
    }
    assert (
        client.put("/api/attendance", headers=academy["coach"], json=data).status_code
        == 400
    )
    booking = db.session.get(CourtBooking, record["booking_id"])
    booking.starts_at = utcnow() - timedelta(hours=2)
    booking.ends_at = utcnow() - timedelta(hours=1)
    db.session.commit()
    assert (
        client.put("/api/attendance", headers=academy["coach"], json=data).status_code
        == 200
    )
    data["status"] = "absent"
    assert (
        client.put("/api/attendance", headers=academy["coach"], json=data).status_code
        == 200
    )
    assert len(client.get("/api/attendance", headers=academy["student"]).json) == 1
    assert (
        client.get("/api/analytics", headers=academy["student"]).json[
            "attendance_percentage"
        ]
        == 0
    )
    assert (
        client.delete(
            f"/api/sessions/{record['id']}", headers=academy["admin"]
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/sessions/{record['id']}",
            headers=academy["admin"],
            json={"court_id": 2},
        ).status_code
        == 400
    )  # past booking cannot move
    assert (
        client.delete(
            f"/api/students/{academy['students'][0]['id']}", headers=academy["admin"]
        ).status_code
        == 409
    )


def test_progress_feedback_and_results(client, academy):
    student_id = academy["students"][0]["id"]
    data = {
        "student_id": student_id,
        "recorded_on": date.today().isoformat(),
        "agility": 70,
        "endurance": 60,
        "footwork": 80,
        "technique": 65,
    }
    record = post(client, academy["coach"], "performance", data)
    assert (
        client.patch(
            f"/api/performance/{record['id']}",
            headers=academy["coach2"],
            json={"agility": 90},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/performance/{record['id']}",
            headers=academy["coach"],
            json={"agility": 101},
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/performance/{record['id']}",
            headers=academy["coach"],
            json={"agility": 90},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/performance", headers=academy["student"], json=data
        ).status_code
        == 403
    )
    assert client.get("/api/performance", headers=academy["coach2"]).json == []
    feedback = post(
        client,
        academy["coach"],
        "feedback",
        {
            "student_id": student_id,
            "recorded_on": date.today().isoformat(),
            "message": "Improve recovery steps",
        },
    )
    assert (
        client.get("/api/feedback", headers=academy["student"]).json[0]["message"]
        == "Improve recovery steps"
    )
    assert (
        client.patch(
            f"/api/feedback/{feedback['id']}",
            headers=academy["coach"],
            json={"message": "Updated"},
        ).status_code
        == 200
    )
    event = post(
        client,
        academy["coach"],
        "tournaments",
        {
            "name": "Junior Open",
            "location": "City Arena",
            "event_date": date.today().isoformat(),
        },
    )
    result = post(
        client,
        academy["coach"],
        "results",
        {
            "student_id": student_id,
            "tournament_id": event["id"],
            "category": "Singles",
            "result": "Winner",
            "achievement": "Gold",
        },
    )
    assert (
        client.get("/api/results", headers=academy["student"]).json[0]["achievement"]
        == "Gold"
    )
    assert (
        client.delete(
            f"/api/tournaments/{event['id']}", headers=academy["admin"]
        ).status_code
        == 409
    )
    for resource, row in [
        ("results", result),
        ("feedback", feedback),
        ("performance", record),
    ]:
        assert (
            client.delete(
                f"/api/{resource}/{row['id']}", headers=academy["coach"]
            ).status_code
            == 204
        )
    assert (
        client.delete(
            f"/api/tournaments/{event['id']}", headers=academy["admin"]
        ).status_code
        == 204
    )


def test_finance_validation_and_balances(client, academy):
    fee = post(
        client,
        academy["admin"],
        "fees",
        {
            "student_id": academy["students"][0]["id"],
            "description": "Training",
            "amount": "1000.00",
            "due_date": date.today().isoformat(),
        },
    )
    data = {
        "fee_id": fee["id"],
        "amount": "400.00",
        "paid_on": date.today().isoformat(),
        "method": "upi",
        "reference": "PAY-001",
    }
    post(client, academy["admin"], "payments", data)
    assert (
        client.post("/api/payments", headers=academy["admin"], json=data).status_code
        == 409
    )
    assert (
        client.post(
            "/api/payments",
            headers=academy["admin"],
            json=dict(data, amount="601.00", reference="PAY-002"),
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/payments",
            headers=academy["admin"],
            json=dict(data, amount="1.001", reference="PAY-003"),
        ).status_code
        == 400
    )
    assert (
        client.get("/api/fees", headers=academy["student"]).json[0]["outstanding"]
        == "600.00"
    )
    assert client.get("/api/fees", headers=academy["coach"]).status_code == 403
    assert client.get("/api/payments", headers=academy["coach2"]).status_code == 403
    assert (
        client.patch(
            f"/api/fees/{fee['id']}",
            headers=academy["admin"],
            json={"amount": "300.00"},
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/api/fees/{fee['id']}", headers=academy["admin"]).status_code
        == 409
    )
    assert (
        client.post("/api/payments", headers=academy["student"], json=data).status_code
        == 403
    )
    assert (
        "outstanding" not in client.get("/api/analytics", headers=academy["coach"]).json
    )


def test_reports_and_validation(client, academy):
    month = date.today().strftime("%Y-%m")
    response = client.get(
        "/api/reports/monthly", headers=academy["admin"], query_string={"month": month}
    )
    assert response.status_code == 200
    assert len(response.json["students"]) == 2
    csv = client.get(
        "/api/reports/monthly",
        headers=academy["admin"],
        query_string={"month": month, "format": "csv"},
    )
    assert csv.status_code == 200 and b"attendance_percentage" in csv.data
    assert (
        client.get(
            "/api/reports/monthly",
            headers=academy["student"],
            query_string={"month": month},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/reports/monthly",
            headers=academy["admin"],
            query_string={"month": "2026-13"},
        ).status_code
        == 400
    )
    assert (
        client.get("/api/analytics", headers=academy["student"]).json[
            "attendance_percentage"
        ]
        is None
    )
    assert client.get("/api/students").status_code == 401
    assert (
        client.post("/api/students", headers=academy["admin"], json=[]).status_code
        == 400
    )


def test_court_inventory_crud(client, academy):
    court = post(client, academy["admin"], "courts", {"name": "Court 3"})
    assert (
        client.patch(
            f"/api/courts/{court['id']}",
            headers=academy["admin"],
            json={"name": "Practice Court"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/courts", headers=academy["coach"], json={"name": "Forbidden"}
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/courts/{court['id']}", headers=academy["admin"]
        ).status_code
        == 204
    )
    booking = session_data(academy)
    post(client, academy["admin"], "sessions", booking)
    assert client.delete("/api/courts/1", headers=academy["admin"]).status_code == 409
