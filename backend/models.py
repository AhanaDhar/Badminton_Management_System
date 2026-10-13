"""Relational domain model. Monetary values use fixed-point decimals."""

from datetime import datetime, timezone
from .extensions import db
from sqlalchemy.dialects import mysql

PRECISE_DATETIME = db.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    login_id = db.Column(db.String(40), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(PRECISE_DATETIME, nullable=False, default=utcnow)
    student = db.relationship("Student", back_populates="user", uselist=False)
    coach = db.relationship("Coach", back_populates="user", uselist=False)
    __table_args__ = (
        db.CheckConstraint("role IN ('ADMIN','COACH','STUDENT')", name="valid_role"),
    )


class Coach(db.Model):
    __tablename__ = "coaches"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False
    )
    specialty = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False, default="")
    user = db.relationship("User", back_populates="coach")
    students = db.relationship("Student", back_populates="coach")


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False
    )
    coach_id = db.Column(
        db.Integer, db.ForeignKey("coaches.id"), nullable=True, index=True
    )
    date_of_birth = db.Column(db.Date, nullable=False)
    joined_on = db.Column(db.Date, nullable=False)
    level = db.Column(db.String(20), nullable=False, default="Beginner")
    phone = db.Column(db.String(30), nullable=False, default="")
    user = db.relationship("User", back_populates="student")
    coach = db.relationship("Coach", back_populates="students")
    __table_args__ = (
        db.CheckConstraint(
            "level IN ('Beginner','Intermediate','Advanced')", name="valid_level"
        ),
    )


class AuthSession(db.Model):
    __tablename__ = "auth_sessions"
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at = db.Column(PRECISE_DATETIME, nullable=False, index=True)
    user = db.relationship("User")


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"
    id = db.Column(db.Integer, primary_key=True)
    key_hash = db.Column(db.String(64), nullable=False, index=True)
    attempted_at = db.Column(
        PRECISE_DATETIME, nullable=False, default=utcnow, index=True
    )


class Court(db.Model):
    __tablename__ = "courts"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False, unique=True)


class CourtBooking(db.Model):
    __tablename__ = "court_bookings"
    id = db.Column(db.Integer, primary_key=True)
    court_id = db.Column(
        db.Integer, db.ForeignKey("courts.id"), nullable=False, index=True
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    starts_at = db.Column(PRECISE_DATETIME, nullable=False, index=True)
    ends_at = db.Column(PRECISE_DATETIME, nullable=False)
    purpose = db.Column(db.String(200), nullable=False)
    court = db.relationship("Court")
    __table_args__ = (
        db.CheckConstraint("ends_at > starts_at", name="booking_positive_duration"),
    )


class TrainingSession(db.Model):
    __tablename__ = "training_sessions"
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(
        db.Integer, db.ForeignKey("coaches.id"), nullable=False, index=True
    )
    booking_id = db.Column(
        db.Integer, db.ForeignKey("court_bookings.id"), unique=True, nullable=False
    )
    title = db.Column(db.String(120), nullable=False)
    focus = db.Column(db.String(200), nullable=False)
    coach = db.relationship("Coach")
    booking = db.relationship("CourtBooking")
    enrollments = db.relationship(
        "Enrollment", cascade="all, delete-orphan", back_populates="session"
    )


class Enrollment(db.Model):
    __tablename__ = "enrollments"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("training_sessions.id"), nullable=False, index=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, index=True
    )
    session = db.relationship("TrainingSession", back_populates="enrollments")
    student = db.relationship("Student")
    __table_args__ = (
        db.UniqueConstraint("session_id", "student_id", name="unique_enrollment"),
    )


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(
        db.Integer, db.ForeignKey("enrollments.id"), nullable=False, unique=True
    )
    status = db.Column(db.String(10), nullable=False)
    marked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    marked_at = db.Column(PRECISE_DATETIME, nullable=False, default=utcnow)
    enrollment = db.relationship("Enrollment")
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('present','absent','excused')", name="valid_attendance"
        ),
    )


class PerformanceRecord(db.Model):
    __tablename__ = "performance_records"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, index=True
    )
    coach_id = db.Column(db.Integer, db.ForeignKey("coaches.id"), nullable=False)
    recorded_on = db.Column(db.Date, nullable=False, index=True)
    agility = db.Column(db.Integer, nullable=False)
    endurance = db.Column(db.Integer, nullable=False)
    footwork = db.Column(db.Integer, nullable=False)
    technique = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(1000), nullable=False, default="")
    student = db.relationship("Student")
    __table_args__ = tuple(
        db.CheckConstraint(f"{m} BETWEEN 0 AND 100", name=f"valid_{m}")
        for m in ("agility", "endurance", "footwork", "technique")
    )


class Feedback(db.Model):
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, index=True
    )
    coach_id = db.Column(db.Integer, db.ForeignKey("coaches.id"), nullable=False)
    recorded_on = db.Column(db.Date, nullable=False)
    message = db.Column(db.String(2000), nullable=False)
    student = db.relationship("Student")
    coach = db.relationship("Coach")


class Fee(db.Model):
    __tablename__ = "fees"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, index=True
    )
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=False, index=True)
    created_on = db.Column(db.Date, nullable=False)
    student = db.relationship("Student")
    payments = db.relationship("Payment", back_populates="fee")
    __table_args__ = (db.CheckConstraint("amount > 0", name="positive_fee"),)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    fee_id = db.Column(db.Integer, db.ForeignKey("fees.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    paid_on = db.Column(db.Date, nullable=False, index=True)
    method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(80), unique=True, nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    fee = db.relationship("Fee", back_populates="payments")
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="positive_payment"),
        db.CheckConstraint(
            "method IN ('cash','bank','card','upi')", name="valid_payment_method"
        ),
    )


class Tournament(db.Model):
    __tablename__ = "tournaments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    event_date = db.Column(db.Date, nullable=False, index=True)


class TournamentResult(db.Model):
    __tablename__ = "tournament_results"
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournaments.id"), nullable=False
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=False, index=True
    )
    coach_id = db.Column(db.Integer, db.ForeignKey("coaches.id"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    result = db.Column(db.String(100), nullable=False)
    achievement = db.Column(db.String(200), nullable=False, default="")
    student = db.relationship("Student")
    tournament = db.relationship("Tournament")
    __table_args__ = (
        db.UniqueConstraint(
            "tournament_id", "student_id", "category", name="unique_tournament_entry"
        ),
    )
