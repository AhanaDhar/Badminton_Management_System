from flask import Blueprint, jsonify
from sqlalchemy import delete, select
from ..extensions import db
from ..models import AuthSession, Coach, Student
from ..services.people import (
    create_user,
    get,
    profile,
    scoped_students,
    student_access,
    update_profile,
)
from ..utils.security import require
from ..utils.validation import APIError, payload

bp = Blueprint("people", __name__, url_prefix="/api")
COMMON = ("name", "email", "password", "phone", "active")
STUDENT_FIELDS = COMMON + ("date_of_birth", "joined_on", "level", "coach_id")
COACH_FIELDS = COMMON + ("specialty",)


@bp.get("/students")
@require()
def students():
    return jsonify(
        [profile(s) for s in db.session.scalars(scoped_students().order_by(Student.id))]
    )


@bp.get("/students/<int:identifier>")
@require()
def student(identifier):
    return jsonify(profile(student_access(identifier)))


@bp.post("/students")
@require("ADMIN")
def add_student():
    data = payload(
        STUDENT_FIELDS + ("login_id",),
        (
            "login_id",
            "name",
            "email",
            "password",
            "date_of_birth",
            "joined_on",
            "level",
        ),
    )
    record = Student(user=create_user("STUDENT", data))
    with db.session.no_autoflush:
        update_profile(record, {k: v for k, v in data.items() if k != "password"})
        db.session.add(record)
    db.session.commit()
    return jsonify(profile(record)), 201


@bp.patch("/students/<int:identifier>")
@require("ADMIN")
def edit_student(identifier):
    record = get(Student, identifier)
    update_profile(record, payload(STUDENT_FIELDS))
    db.session.commit()
    return jsonify(profile(record))


@bp.get("/coaches")
@require("ADMIN", "COACH")
def coaches():
    from flask import g

    query = select(Coach).order_by(Coach.id)
    if g.user.role == "COACH":
        query = query.where(Coach.user_id == g.user.id)
    return jsonify([profile(c) for c in db.session.scalars(query)])


@bp.post("/coaches")
@require("ADMIN")
def add_coach():
    data = payload(
        COACH_FIELDS + ("login_id",),
        ("login_id", "name", "email", "password", "specialty"),
    )
    record = Coach(user=create_user("COACH", data))
    with db.session.no_autoflush:
        update_profile(record, {k: v for k, v in data.items() if k != "password"})
        db.session.add(record)
    db.session.commit()
    return jsonify(profile(record)), 201


@bp.patch("/coaches/<int:identifier>")
@require("ADMIN")
def edit_coach(identifier):
    record = get(Coach, identifier)
    update_profile(record, payload(COACH_FIELDS))
    db.session.commit()
    return jsonify(profile(record))


@bp.delete("/students/<int:identifier>")
@bp.delete("/coaches/<int:identifier>")
@require("ADMIN")
def delete_person(identifier):
    from flask import request

    model = Student if "/students/" in request.path else Coach
    record = get(model, identifier)
    if model is Coach and record.students:
        raise APIError("Reassign students before deleting a coach", 409)
    user = record.user
    db.session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.session.delete(record)
    db.session.flush()  # Foreign keys protect academic and financial history.
    db.session.delete(user)
    db.session.commit()
    return "", 204
