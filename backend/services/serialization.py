from datetime import date, datetime
from decimal import Decimal
from ..models import (
    Attendance,
    CourtBooking,
    Fee,
    Feedback,
    Payment,
    PerformanceRecord,
    TournamentResult,
    TrainingSession,
)


def scalar(value):
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def serialize(record):
    data = {c.name: scalar(getattr(record, c.name)) for c in record.__table__.columns}
    if isinstance(record, CourtBooking):
        data.update(court_name=record.court.name)
    if isinstance(record, TrainingSession):
        data.update(
            coach_name=record.coach.user.name,
            court_id=record.booking.court_id,
            court_name=record.booking.court.name,
            starts_at=scalar(record.booking.starts_at),
            ends_at=scalar(record.booking.ends_at),
            student_ids=[e.student_id for e in record.enrollments],
        )
    if isinstance(record, Attendance):
        data.update(
            student_id=record.enrollment.student_id,
            student_name=record.enrollment.student.user.name,
            session_id=record.enrollment.session_id,
            session_title=record.enrollment.session.title,
            starts_at=scalar(record.enrollment.session.booking.starts_at),
        )
    if isinstance(record, (PerformanceRecord, Feedback, Fee, TournamentResult)):
        data["student_name"] = record.student.user.name
    if isinstance(record, Feedback):
        data["coach_name"] = record.coach.user.name
    if isinstance(record, Fee):
        paid = sum((p.amount for p in record.payments), Decimal("0.00"))
        data.update(paid=str(paid), outstanding=str(record.amount - paid))
    if isinstance(record, Payment):
        data.update(
            student_id=record.fee.student_id,
            student_name=record.fee.student.user.name,
            description=record.fee.description,
        )
    if isinstance(record, TournamentResult):
        data.update(
            tournament_name=record.tournament.name,
            event_date=scalar(record.tournament.event_date),
        )
    return data
