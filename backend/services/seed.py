"""Deterministic fictional data; passwords are supplied at invocation and hashed."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from sqlalchemy import select
from ..extensions import db
from ..models import (
    Attendance,
    Coach,
    Court,
    CourtBooking,
    Enrollment,
    Fee,
    Feedback,
    Payment,
    PerformanceRecord,
    Student,
    Tournament,
    TournamentResult,
    TrainingSession,
    User,
)
from ..utils.validation import APIError, password as validate_password
from ..utils.time import academy_today
from .people import create_user


def seed(password):
    validate_password(password)
    if db.session.scalar(select(User.id).limit(1)):
        raise APIError(
            "Demo seeding requires an empty users table; existing data is never overwritten",
            409,
        )
    today = academy_today()
    admin = create_user(
        "ADMIN",
        {
            "login_id": "ADM001",
            "name": "Academy Administrator",
            "email": "admin@example.com",
            "password": password,
        },
    )
    coaches = []
    for index, (name, specialty) in enumerate(
        (
            ("Ananya Rao", "Footwork & singles technique"),
            ("Vikram Shah", "Doubles tactics & conditioning"),
        ),
        1,
    ):
        user = create_user(
            "COACH",
            {
                "login_id": f"C00{index}",
                "name": name,
                "email": f"coach{index}@example.com",
                "password": password,
            },
        )
        coach = Coach(
            user_id=user.id, specialty=specialty, phone=f"+91 90000 0100{index}"
        )
        db.session.add(coach)
        coaches.append(coach)
    courts = [Court(name=f"Court {i}") for i in range(1, 4)]
    db.session.add_all(courts)
    db.session.flush()
    students = []
    for index, name in enumerate(
        (
            "Aarav Mehta",
            "Isha Kapoor",
            "Kabir Nair",
            "Meera Joshi",
            "Rohan Das",
            "Tara Singh",
        ),
        1,
    ):
        user = create_user(
            "STUDENT",
            {
                "login_id": f"S00{index}",
                "name": name,
                "email": f"student{index}@example.com",
                "password": password,
            },
        )
        student = Student(
            user_id=user.id,
            coach_id=coaches[(index - 1) // 3].id,
            date_of_birth=date(today.year - 15 - index % 3, 5, 10 + index),
            joined_on=today - timedelta(days=130),
            level=["Beginner", "Intermediate", "Advanced"][(index - 1) % 3],
            phone=f"+91 90000 0200{index}",
        )
        db.session.add(student)
        students.append(student)
    db.session.flush()
    for week in range(8):
        recorded = today - timedelta(days=(8 - week) * 7)
        for index, student in enumerate(students):
            base = 40 + index * 3 + week * 4
            db.session.add(
                PerformanceRecord(
                    student_id=student.id,
                    coach_id=student.coach_id,
                    recorded_on=recorded,
                    agility=base,
                    endurance=base + 3,
                    footwork=base + 6,
                    technique=base + 4,
                    notes="Weekly skills assessment",
                )
            )
    for coach_index, coach in enumerate(coaches):
        group = [s for s in students if s.coach_id == coach.id]
        for index, offset in enumerate((-28, -21, -14, -7, 1, 3, 5)):
            start = datetime.combine(
                today + timedelta(days=offset), time(10 + coach_index * 2)
            )
            booking = CourtBooking(
                court_id=courts[coach_index].id,
                created_by=admin.id,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                purpose="Academy training",
            )
            db.session.add(booking)
            db.session.flush()
            session = TrainingSession(
                coach_id=coach.id,
                booking_id=booking.id,
                title="Footwork & match play",
                focus="Split step, recovery, and rally consistency",
            )
            db.session.add(session)
            db.session.flush()
            for student in group:
                enrollment = Enrollment(session_id=session.id, student_id=student.id)
                db.session.add(enrollment)
                db.session.flush()
                if offset < 0:
                    status = "absent" if (student.id + index) % 5 == 0 else "present"
                    db.session.add(
                        Attendance(
                            enrollment_id=enrollment.id,
                            status=status,
                            marked_by=coach.user_id,
                            marked_at=start + timedelta(hours=1),
                        )
                    )
    for student in students:
        db.session.add(
            Feedback(
                student_id=student.id,
                coach_id=student.coach_id,
                recorded_on=today - timedelta(days=2),
                message="Your recovery steps are improving. Practice 3 × 2-minute shadow-footwork sets, then focus on a balanced landing after each overhead.",
            )
        )
        for offset in (2, 1, 0):
            month_index = today.year * 12 + today.month - 1 - offset
            year, month_number = divmod(month_index, 12)
            month = date(year, month_number + 1, 1)
            fee = Fee(
                student_id=student.id,
                description=f"Training fee · {month:%B %Y}",
                amount=Decimal("2500.00"),
                due_date=month + timedelta(days=9),
                created_on=month,
            )
            db.session.add(fee)
            db.session.flush()
            if offset > 0 or student.id % 2 == 0:
                paid_on = min(month + timedelta(days=4), today)
                amount = Decimal("1500.00") if offset == 0 else Decimal("2500.00")
                db.session.add(
                    Payment(
                        fee_id=fee.id,
                        amount=amount,
                        paid_on=paid_on,
                        method="upi",
                        reference=f"DEMO-{student.id}-{offset}",
                        recorded_by=admin.id,
                    )
                )
    tournament = Tournament(
        name="District Junior Open",
        location="City Sports Complex",
        event_date=today - timedelta(days=10),
    )
    db.session.add(tournament)
    db.session.flush()
    for index, student in enumerate(students[:4]):
        db.session.add(
            TournamentResult(
                tournament_id=tournament.id,
                student_id=student.id,
                coach_id=student.coach_id,
                category="U19 Singles",
                result=["Winner", "Runner-up", "Quarter-finalist", "Round of 16"][
                    index
                ],
                achievement=["Gold medal", "Silver medal", "", ""][index],
            )
        )
    db.session.commit()
