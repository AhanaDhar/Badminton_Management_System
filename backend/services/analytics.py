"""Pandas aggregation for scoped dashboard metrics and monthly exports."""

import calendar
import os
from zoneinfo import ZoneInfo
from datetime import timezone
from datetime import date, datetime, time
from decimal import Decimal
import pandas as pd
from sqlalchemy import select
from ..extensions import db
from ..models import (
    Attendance,
    CourtBooking,
    Enrollment,
    Fee,
    Payment,
    PerformanceRecord,
    TournamentResult,
    TrainingSession,
    utcnow,
)
from .people import scoped_students, student_ids
from .serialization import serialize


def attendance_counts(ids, start=None, end=None):
    query = (
        select(Enrollment)
        .join(TrainingSession)
        .join(CourtBooking)
        .where(Enrollment.student_id.in_(ids), CourtBooking.starts_at <= utcnow())
    )
    if start:
        query = query.where(
            CourtBooking.starts_at >= start, CourtBooking.starts_at < end
        )
    enrolled = list(db.session.scalars(query))
    marks = {
        a.enrollment_id: a.status
        for a in db.session.scalars(
            select(Attendance).where(
                Attendance.enrollment_id.in_([e.id for e in enrolled])
            )
        )
    }
    counts = {
        identifier: {
            "scheduled": 0,
            "present": 0,
            "absent": 0,
            "excused": 0,
            "unmarked": 0,
        }
        for identifier in ids
    }
    for enrollment in enrolled:
        row = counts[enrollment.student_id]
        row["scheduled"] += 1
        row[marks.get(enrollment.id, "unmarked")] += 1
    for row in counts.values():
        denominator = row["scheduled"] - row["excused"]
        row["attendance_percentage"] = (
            round(100 * row["present"] / denominator, 1) if denominator else None
        )
    return counts


def dashboard(role):
    students = list(db.session.scalars(scoped_students()))
    ids = [s.id for s in students]
    counts = attendance_counts(ids)
    records = [
        serialize(p)
        for p in db.session.scalars(
            select(PerformanceRecord)
            .where(PerformanceRecord.student_id.in_(ids))
            .order_by(PerformanceRecord.recorded_on, PerformanceRecord.id)
        )
    ]
    results = list(
        db.session.scalars(
            select(TournamentResult).where(TournamentResult.student_id.in_(ids))
        )
    )
    total = sum(c["scheduled"] - c["excused"] for c in counts.values())
    present = sum(c["present"] for c in counts.values())
    response = {
        "students": len(students),
        "active_students": sum(s.user.active for s in students),
        "attendance_percentage": round(100 * present / total, 1) if total else None,
        "unmarked_attendance": sum(c["unmarked"] for c in counts.values()),
        "attendance_by_student": [
            {"student_id": s.id, "name": s.user.name, **counts[s.id]} for s in students
        ],
        "performance": records,
        "tournament_entries": len(results),
        "achievements": sum(bool(r.achievement) for r in results),
    }
    if records:
        frame = pd.DataFrame(records)
        response["performance_monthly"] = (
            frame.assign(month=frame.recorded_on.str[:7])
            .groupby("month")[["agility", "endurance", "footwork", "technique"]]
            .mean()
            .round(1)
            .reset_index()
            .to_dict("records")
        )
    else:
        response["performance_monthly"] = []
    if role in ("ADMIN", "STUDENT"):
        fees = [
            serialize(f)
            for f in db.session.scalars(select(Fee).where(Fee.student_id.in_(ids)))
        ]
        payments = [
            serialize(p)
            for p in db.session.scalars(
                select(Payment).join(Fee).where(Fee.student_id.in_(ids))
            )
        ]
        response.update(
            outstanding=str(
                sum((Decimal(f["outstanding"]) for f in fees), Decimal("0.00"))
            ),
            collected=str(
                sum((Decimal(p["amount"]) for p in payments), Decimal("0.00"))
            ),
        )
        frame = pd.DataFrame(payments)
        response["collections_monthly"] = (
            []
            if frame.empty
            else frame.assign(
                month=frame.paid_on.str[:7], amount=frame.amount.map(float)
            )
            .groupby("month")
            .amount.sum()
            .round(2)
            .reset_index()
            .to_dict("records")
        )
    if role == "ADMIN":
        from ..models import Coach

        response["coaches"] = len(list(db.session.scalars(select(Coach))))
        response["level_distribution"] = (
            pd.Series([s.level for s in students], dtype="object")
            .value_counts()
            .rename_axis("level")
            .reset_index(name="count")
            .to_dict("records")
        )
    return response


def monthly_report(year, month):
    start_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    next_day = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    students = list(db.session.scalars(scoped_students()))
    ids = student_ids()
    zone = ZoneInfo(os.getenv("ACADEMY_TIMEZONE", "Asia/Kolkata"))
    start_utc = (
        datetime.combine(start_day, time.min, zone)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    end_utc = (
        datetime.combine(next_day, time.min, zone)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    counts = attendance_counts(ids, start_utc, end_utc)
    fees = list(db.session.scalars(select(Fee).where(Fee.created_on <= last_day)))
    payments = list(
        db.session.scalars(select(Payment).where(Payment.paid_on <= last_day))
    )
    fee_map = {f.id: f for f in fees}
    paid_by_fee = {}
    for payment in payments:
        paid_by_fee[payment.fee_id] = (
            paid_by_fee.get(payment.fee_id, Decimal("0")) + payment.amount
        )
    rows = []
    for student in students:
        student_fees = [f for f in fees if f.student_id == student.id]
        received = sum(
            (
                p.amount
                for p in payments
                if p.fee_id in fee_map
                and fee_map[p.fee_id].student_id == student.id
                and p.paid_on >= start_day
            ),
            Decimal("0.00"),
        )
        due = sum(
            (f.amount for f in student_fees if start_day <= f.due_date <= last_day),
            Decimal("0.00"),
        )
        balance = sum(
            (f.amount - paid_by_fee.get(f.id, Decimal("0")) for f in student_fees),
            Decimal("0.00"),
        )
        rows.append(
            {
                "student_id": student.id,
                "name": student.user.name,
                "level": student.level,
                **counts[student.id],
                "fees_due_this_month": str(due),
                "collected_this_month": str(received),
                "outstanding_at_month_end": str(balance),
            }
        )
    performance = [
        serialize(r)
        for r in db.session.scalars(
            select(PerformanceRecord).where(
                PerformanceRecord.recorded_on >= start_day,
                PerformanceRecord.recorded_on < next_day,
            )
        )
    ]
    frame = pd.DataFrame(performance)
    averages = (
        {}
        if frame.empty
        else frame[["agility", "endurance", "footwork", "technique"]]
        .mean()
        .round(1)
        .to_dict()
    )
    return {
        "month": f"{year:04d}-{month:02d}",
        "students": rows,
        "performance_averages": averages,
        "collected": str(
            sum((Decimal(r["collected_this_month"]) for r in rows), Decimal("0.00"))
        ),
        "outstanding": str(
            sum((Decimal(r["outstanding_at_month_end"]) for r in rows), Decimal("0.00"))
        ),
    }
