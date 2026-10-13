from datetime import timedelta
from flask import g
from sqlalchemy import select
from ..extensions import db
from ..models import (
    Attendance,
    Coach,
    Court,
    CourtBooking,
    Enrollment,
    Student,
    TrainingSession,
    utcnow,
)
from ..utils.validation import APIError, instant, integer, text
from .people import get


def session_access(identifier):
    record = get(TrainingSession, identifier)
    if g.user.role == "COACH" and record.coach_id != g.user.coach.id:
        raise APIError("Session belongs to another coach", 403)
    if g.user.role == "STUDENT" and g.user.student.id not in [
        e.student_id for e in record.enrollments
    ]:
        raise APIError("You are not enrolled in this session", 403)
    return record


def reserve(data, existing=None):
    court_id = integer(
        data.get("court_id", existing.court_id if existing else None), "court_id"
    )
    start = (
        instant(data["starts_at"], "starts_at")
        if "starts_at" in data
        else (existing.starts_at if existing else None)
    )
    end = (
        instant(data["ends_at"], "ends_at")
        if "ends_at" in data
        else (existing.ends_at if existing else None)
    )
    if start is None or end is None or end <= start or end - start > timedelta(hours=8):
        raise APIError("Booking duration must be between 0 and 8 hours")
    if start < utcnow() and (
        existing is None
        or start != existing.starts_at
        or end != existing.ends_at
        or court_id != existing.court_id
    ):
        raise APIError("Cannot create or move a booking into the past")
    # Serialize every writer on the court row; overlapping inserts cannot race on MySQL.
    ids = sorted({court_id, existing.court_id} if existing else {court_id})
    locked = list(
        db.session.scalars(
            select(Court).where(Court.id.in_(ids)).order_by(Court.id).with_for_update()
        )
    )
    if len(locked) != len(ids):
        raise APIError("Court not found", 404)
    conflict = select(CourtBooking).where(
        CourtBooking.court_id == court_id,
        CourtBooking.starts_at < end,
        CourtBooking.ends_at > start,
    )
    if existing:
        conflict = conflict.where(CourtBooking.id != existing.id)
    # Locking reads use current data under MySQL REPEATABLE READ.
    if db.session.scalar(conflict.with_for_update()):
        raise APIError("Court is already booked during this time", 409)
    record = existing or CourtBooking(created_by=g.user.id)
    record.court_id, record.starts_at, record.ends_at = court_id, start, end
    record.purpose = text(
        data.get("purpose", record.purpose or "Training"), "purpose", 200
    )
    db.session.add(record)
    db.session.flush()
    return record


def save_session(data, record=None):
    coach_id = integer(
        data.get("coach_id", record.coach_id if record else None), "coach_id"
    )
    if g.user.role == "COACH" and coach_id != g.user.coach.id:
        raise APIError("Cannot create a schedule for another coach", 403)
    # Coach lock also prevents simultaneous sessions on different courts.
    coach = db.session.scalar(
        select(Coach).where(Coach.id == coach_id).with_for_update()
    )
    if coach is None or not coach.user.active:
        raise APIError("An active coach is required")
    if record and coach_id != record.coach_id:
        raise APIError("Session coach cannot change; recreate the session instead")
    students = data.get(
        "student_ids", [e.student_id for e in record.enrollments] if record else []
    )
    if not isinstance(students, list) or len(students) > 100:
        raise APIError("student_ids must be a list of at most 100 IDs")
    students = [integer(s, "student_id") for s in students]
    if len(set(students)) != len(students) or not students:
        raise APIError("Select at least one student; duplicate IDs are not allowed")
    for identifier in students:
        student = get(Student, identifier)
        if student.coach_id != coach_id or not student.user.active:
            raise APIError(
                "Every student must be active and assigned to the session coach"
            )
    booking = reserve(data, record.booking if record else None)
    overlapping = (
        select(TrainingSession)
        .join(CourtBooking)
        .where(
            TrainingSession.coach_id == coach_id,
            CourtBooking.starts_at < booking.ends_at,
            CourtBooking.ends_at > booking.starts_at,
        )
    )
    if record:
        overlapping = overlapping.where(TrainingSession.id != record.id)
    if db.session.scalar(overlapping.with_for_update()):
        raise APIError("Coach already has a training session during this time", 409)
    if record and db.session.scalar(
        select(Attendance).join(Enrollment).where(Enrollment.session_id == record.id)
    ):
        if set(students) != {e.student_id for e in record.enrollments} or any(
            k in data for k in ("starts_at", "ends_at", "court_id")
        ):
            raise APIError("Attendance exists; timing and enrollment are locked", 409)
    if record is None:
        record = TrainingSession(coach_id=coach_id, booking_id=booking.id)
        db.session.add(record)
    record.title = text(data.get("title", record.title), "title", 120)
    record.focus = text(data.get("focus", record.focus), "focus", 200)
    existing = {e.student_id: e for e in record.enrollments}
    for identifier, enrollment in existing.items():
        if identifier not in students:
            record.enrollments.remove(enrollment)
    for identifier in students:
        if identifier not in existing:
            record.enrollments.append(Enrollment(student_id=identifier))
    db.session.flush()
    return record
