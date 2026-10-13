from ..utils.time import academy_today
from decimal import Decimal
from flask import Blueprint, g, jsonify
from sqlalchemy import select
from ..extensions import db
from ..models import Fee, Payment
from ..services.people import get, student_access, student_ids
from ..services.serialization import serialize
from ..utils.security import require
from ..utils.validation import APIError, choice, day, integer, money, payload, text

bp = Blueprint("finance", __name__, url_prefix="/api")


@bp.get("/fees")
@require("ADMIN", "STUDENT")
def fees():
    return jsonify(
        [
            serialize(f)
            for f in db.session.scalars(
                select(Fee)
                .where(Fee.student_id.in_(student_ids()))
                .order_by(Fee.due_date)
            )
        ]
    )


@bp.get("/payments")
@require("ADMIN", "STUDENT")
def payments():
    query = (
        select(Payment)
        .join(Fee)
        .where(Fee.student_id.in_(student_ids()))
        .order_by(Payment.paid_on)
    )
    return jsonify([serialize(p) for p in db.session.scalars(query)])


def save_fee(data, record=None):
    record = record or Fee(created_on=academy_today())
    if "student_id" in data:
        identifier = integer(data["student_id"], "student_id")
        student_access(identifier)
        if record.id and identifier != record.student_id:
            raise APIError("Fee student cannot change")
        record.student_id = identifier
    if "amount" in data:
        amount = money(data["amount"])
        paid = (
            sum(
                (
                    p.amount
                    for p in db.session.scalars(
                        select(Payment)
                        .where(Payment.fee_id == record.id)
                        .with_for_update()
                    )
                ),
                Decimal("0"),
            )
            if record.id
            else Decimal("0")
        )
        if amount < paid:
            raise APIError("Fee amount cannot be below total payments", 409)
        record.amount = amount
    if "description" in data:
        record.description = text(data["description"], "description", 200)
    if "due_date" in data:
        record.due_date = day(data["due_date"], "due_date")
    db.session.add(record)
    db.session.commit()
    return record


@bp.post("/fees")
@require("ADMIN")
def add_fee():
    fields = ("student_id", "description", "amount", "due_date")
    return jsonify(serialize(save_fee(payload(fields, fields)))), 201


@bp.patch("/fees/<int:identifier>")
@require("ADMIN")
def edit_fee(identifier):
    record = db.session.scalar(
        select(Fee).where(Fee.id == identifier).with_for_update()
    )
    if not record:
        raise APIError("Fee not found", 404)
    return jsonify(
        serialize(
            save_fee(
                payload(("student_id", "description", "amount", "due_date")), record
            )
        )
    )


@bp.delete("/fees/<int:identifier>")
@require("ADMIN")
def delete_fee(identifier):
    record = get(Fee, identifier)
    if record.payments:
        raise APIError("Cannot delete a fee with payment history", 409)
    db.session.delete(record)
    db.session.commit()
    return "", 204


@bp.post("/payments")
@require("ADMIN")
def add_payment():
    fields = ("fee_id", "amount", "paid_on", "method", "reference")
    data = payload(fields, fields)
    identifier = integer(data["fee_id"], "fee_id")
    fee = db.session.scalar(select(Fee).where(Fee.id == identifier).with_for_update())
    if fee is None:
        raise APIError("Fee not found", 404)
    amount = money(data["amount"])
    paid = sum(
        (
            p.amount
            for p in db.session.scalars(
                select(Payment).where(Payment.fee_id == fee.id).with_for_update()
            )
        ),
        Decimal("0"),
    )
    if paid + amount > fee.amount:
        raise APIError("Payment exceeds outstanding fee balance", 409)
    paid_on = day(data["paid_on"], "paid_on")
    if paid_on > academy_today() or paid_on < fee.created_on:
        raise APIError("Payment date must be between fee creation and today")
    record = Payment(
        fee_id=fee.id,
        amount=amount,
        paid_on=paid_on,
        method=choice(data["method"], "method", ("cash", "bank", "card", "upi")),
        reference=text(data["reference"], "reference", 80),
        recorded_by=g.user.id,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify(serialize(record)), 201
