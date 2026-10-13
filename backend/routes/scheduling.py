from flask import Blueprint, g, jsonify
from sqlalchemy import select
from ..extensions import db
from ..models import (
    Attendance,
    Court,
    CourtBooking,
    Enrollment,
    TrainingSession,
    utcnow,
)
from ..services.people import get, student_access
from ..services.scheduling import reserve, save_session, session_access
from ..services.serialization import serialize
from ..utils.security import require
from ..utils.validation import APIError, choice, integer, payload, text

bp = Blueprint("scheduling", __name__, url_prefix="/api")
BOOKING_FIELDS = ("court_id", "starts_at", "ends_at", "purpose")
SESSION_FIELDS = (
    "coach_id",
    "title",
    "focus",
    "student_ids",
    "court_id",
    "starts_at",
    "ends_at",
)


@bp.get("/courts")
@require("ADMIN", "COACH")
def courts():
    return jsonify(
        [serialize(c) for c in db.session.scalars(select(Court).order_by(Court.id))]
    )


@bp.get("/bookings")
@require("ADMIN", "COACH")
def bookings():
    # Court availability is shared; no personal booking creator data for coaches.
    rows = [
        serialize(b)
        for b in db.session.scalars(
            select(CourtBooking).order_by(CourtBooking.starts_at)
        )
    ]
    if g.user.role == "COACH":
        for row in rows:
            row.pop("created_by")
    return jsonify(rows)


@bp.post("/bookings")
@require("ADMIN")
def add_booking():
    record = reserve(payload(BOOKING_FIELDS, BOOKING_FIELDS))
    db.session.commit()
    return jsonify(serialize(record)), 201


@bp.patch("/bookings/<int:identifier>")
@require("ADMIN")
def edit_booking(identifier):
    record = get(CourtBooking, identifier)
    if db.session.scalar(
        select(TrainingSession).where(TrainingSession.booking_id == identifier)
    ):
        raise APIError("Edit this booking through its training session", 409)
    reserve(payload(BOOKING_FIELDS), record)
    db.session.commit()
    return jsonify(serialize(record))


@bp.delete("/bookings/<int:identifier>")
@require("ADMIN")
def delete_booking(identifier):
    db.session.delete(get(CourtBooking, identifier))
    db.session.commit()
    return "", 204


@bp.get("/sessions")
@require()
def sessions():
    query = select(TrainingSession).join(CourtBooking).order_by(CourtBooking.starts_at)
    if g.user.role == "COACH":
        query = query.where(TrainingSession.coach_id == g.user.coach.id)
    if g.user.role == "STUDENT":
        query = query.join(Enrollment).where(Enrollment.student_id == g.user.student.id)
    rows = [serialize(s) for s in db.session.scalars(query)]
    if g.user.role == "STUDENT":
        for row in rows:
            row.pop("student_ids")
    return jsonify(rows)


@bp.post("/sessions")
@require("ADMIN", "COACH")
def add_session():
    record = save_session(payload(SESSION_FIELDS, SESSION_FIELDS))
    db.session.commit()
    return jsonify(serialize(record)), 201


@bp.patch("/sessions/<int:identifier>")
@require("ADMIN", "COACH")
def edit_session(identifier):
    record = save_session(payload(SESSION_FIELDS), session_access(identifier))
    db.session.commit()
    return jsonify(serialize(record))


@bp.delete("/sessions/<int:identifier>")
@require("ADMIN", "COACH")
def delete_session(identifier):
    record = session_access(identifier)
    if db.session.scalar(
        select(Attendance).join(Enrollment).where(Enrollment.session_id == identifier)
    ):
        raise APIError("Cannot delete a session with attendance history", 409)
    booking = record.booking
    db.session.delete(record)
    db.session.flush()
    db.session.delete(booking)
    db.session.commit()
    return "", 204


@bp.get("/attendance")
@require()
def attendance():
    from ..services.people import student_ids

    query = (
        select(Attendance)
        .join(Enrollment)
        .where(Enrollment.student_id.in_(student_ids()))
        .order_by(Attendance.id)
    )
    return jsonify([serialize(a) for a in db.session.scalars(query)])


@bp.put("/attendance")
@require("ADMIN", "COACH")
def mark_attendance():
    data = payload(
        ("session_id", "student_id", "status"), ("session_id", "student_id", "status")
    )
    session = session_access(integer(data["session_id"], "session_id"))
    student_access(integer(data["student_id"], "student_id"))
    if session.booking.starts_at > utcnow():
        raise APIError("Cannot mark attendance before a session starts")
    enrollment = db.session.scalar(
        select(Enrollment)
        .where(
            Enrollment.session_id == session.id,
            Enrollment.student_id == data["student_id"],
        )
        .with_for_update()
    )
    if not enrollment:
        raise APIError("Student is not enrolled in this session")
    status = choice(data["status"], "status", ("present", "absent", "excused"))
    record = db.session.scalar(
        select(Attendance)
        .where(Attendance.enrollment_id == enrollment.id)
        .with_for_update()
    )
    if record is None:
        record = Attendance(enrollment_id=enrollment.id)
        db.session.add(record)
    record.status, record.marked_by, record.marked_at = status, g.user.id, utcnow()
    db.session.commit()
    return jsonify(serialize(record))


@bp.post("/courts")
@require("ADMIN")
def add_court():
    data = payload(("name",), ("name",))
    court = Court(name=text(data["name"], "name", 60))
    db.session.add(court)
    db.session.commit()
    return jsonify(serialize(court)), 201


@bp.patch("/courts/<int:identifier>")
@require("ADMIN")
def edit_court(identifier):
    court = get(Court, identifier)
    data = payload(("name",), ("name",))
    court.name = text(data["name"], "name", 60)
    db.session.commit()
    return jsonify(serialize(court))


@bp.delete("/courts/<int:identifier>")
@require("ADMIN")
def delete_court(identifier):
    db.session.delete(get(Court, identifier))
    db.session.commit()
    return "", 204
