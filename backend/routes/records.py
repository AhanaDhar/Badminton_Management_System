"""Student progress, coach feedback, and tournament participation."""

from ..utils.time import academy_today
from flask import Blueprint, g, jsonify
from sqlalchemy import select
from ..extensions import db
from ..models import Coach, Feedback, PerformanceRecord, Tournament, TournamentResult
from ..services.people import get, student_access, student_ids
from ..services.serialization import serialize
from ..utils.security import require
from ..utils.validation import APIError, day, integer, payload, text

bp = Blueprint("records", __name__, url_prefix="/api")
CONFIG = {
    "performance": (
        PerformanceRecord,
        (
            "student_id",
            "recorded_on",
            "agility",
            "endurance",
            "footwork",
            "technique",
            "notes",
        ),
        ("student_id", "recorded_on", "agility", "endurance", "footwork", "technique"),
    ),
    "feedback": (
        Feedback,
        ("student_id", "recorded_on", "message"),
        ("student_id", "recorded_on", "message"),
    ),
    "results": (
        TournamentResult,
        ("student_id", "tournament_id", "category", "result", "achievement"),
        ("student_id", "tournament_id", "category", "result"),
    ),
}


def config(resource):
    if resource not in CONFIG:
        raise APIError("Resource not found", 404)
    return CONFIG[resource]


def write_record(resource, data, record=None):
    model, _, _ = config(resource)
    student_id = integer(
        data.get("student_id", record.student_id if record else None), "student_id"
    )
    student = student_access(student_id)
    if record and student_id != record.student_id:
        raise APIError("Student cannot change on an existing record")
    if g.user.role == "COACH":
        coach_id = g.user.coach.id
        if record and record.coach_id != coach_id:
            raise APIError("Cannot change another coach's record", 403)
    else:
        coach_id = record.coach_id if record else student.coach_id
    if coach_id is None or (record is None and not get(Coach, coach_id).user.active):
        raise APIError("An active assigned coach is required")
    record = record or model(student_id=student_id, coach_id=coach_id)
    for key, value in data.items():
        if key == "student_id":
            continue
        if key == "recorded_on":
            value = day(value, key)
            if value > academy_today():
                raise APIError("Record date cannot be in the future")
        elif key in ("agility", "endurance", "footwork", "technique"):
            value = integer(value, key, 0, 100)
        elif key == "tournament_id":
            value = get(Tournament, integer(value, key)).id
        else:
            limits = {
                "notes": 1000,
                "message": 2000,
                "category": 80,
                "result": 100,
                "achievement": 200,
            }
            value = text(value, key, limits[key], empty=key in ("notes", "achievement"))
        setattr(record, key, value)
    db.session.add(record)
    db.session.commit()
    return record


@bp.get("/performance")
@bp.get("/feedback")
@bp.get("/results")
@require()
def list_records():
    from flask import request

    resource = request.path.rsplit("/", 1)[1]
    model, _, _ = config(resource)
    query = select(model).where(model.student_id.in_(student_ids())).order_by(model.id)
    return jsonify([serialize(r) for r in db.session.scalars(query)])


@bp.post("/performance")
@bp.post("/feedback")
@bp.post("/results")
@require("ADMIN", "COACH")
def add_record():
    from flask import request

    resource = request.path.rsplit("/", 1)[1]
    _, fields, required = config(resource)
    return jsonify(serialize(write_record(resource, payload(fields, required)))), 201


@bp.patch("/performance/<int:identifier>")
@bp.patch("/feedback/<int:identifier>")
@bp.patch("/results/<int:identifier>")
@require("ADMIN", "COACH")
def edit_record(identifier):
    from flask import request

    resource = request.path.split("/")[2]
    model, fields, _ = config(resource)
    record = get(model, identifier)
    student_access(record.student_id)
    return jsonify(serialize(write_record(resource, payload(fields), record)))


@bp.delete("/performance/<int:identifier>")
@bp.delete("/feedback/<int:identifier>")
@bp.delete("/results/<int:identifier>")
@require("ADMIN", "COACH")
def delete_record(identifier):
    from flask import request

    model, _, _ = config(request.path.split("/")[2])
    record = get(model, identifier)
    student_access(record.student_id)
    if g.user.role == "COACH" and record.coach_id != g.user.coach.id:
        raise APIError("Cannot delete another coach's record", 403)
    db.session.delete(record)
    db.session.commit()
    return "", 204


@bp.get("/tournaments")
@require()
def tournaments():
    query = select(Tournament).order_by(Tournament.event_date)
    if g.user.role == "STUDENT":
        query = (
            query.join(TournamentResult)
            .where(TournamentResult.student_id == g.user.student.id)
            .distinct()
        )
    return jsonify([serialize(t) for t in db.session.scalars(query)])


def save_tournament(data, record=None):
    record = record or Tournament()
    for key, value in data.items():
        setattr(
            record,
            key,
            day(value, key) if key == "event_date" else text(value, key, 120),
        )
    db.session.add(record)
    db.session.commit()
    return record


@bp.post("/tournaments")
@require("ADMIN", "COACH")
def add_tournament():
    fields = ("name", "location", "event_date")
    return jsonify(serialize(save_tournament(payload(fields, fields)))), 201


@bp.patch("/tournaments/<int:identifier>")
@require("ADMIN")
def edit_tournament(identifier):
    return jsonify(
        serialize(
            save_tournament(
                payload(("name", "location", "event_date")), get(Tournament, identifier)
            )
        )
    )


@bp.delete("/tournaments/<int:identifier>")
@require("ADMIN")
def delete_tournament(identifier):
    db.session.delete(get(Tournament, identifier))
    db.session.commit()
    return "", 204
