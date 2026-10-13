from ..utils.time import academy_today
import re
from flask import g
from sqlalchemy import delete, select
from werkzeug.security import generate_password_hash
from ..extensions import db
from ..models import AuthSession, Coach, Student, User
from ..utils.validation import APIError, choice, day, email, integer, password, text


def get(model, identifier):
    record = db.session.get(model, identifier)
    if record is None:
        raise APIError("Record not found", 404)
    return record


def create_user(role, data):
    login_id = text(data["login_id"], "login_id", 40).upper()
    if not re.fullmatch(r"[A-Z0-9_-]+", login_id):
        raise APIError("ID may contain letters, numbers, underscores and hyphens")
    user = User(
        role=role,
        login_id=login_id,
        name=text(data["name"], "name", 100),
        email=email(data["email"]),
        password_hash=generate_password_hash(password(data["password"])),
    )
    db.session.add(user)
    db.session.flush()
    return user


def student_access(student_id):
    student = get(Student, student_id)
    if g.user.role == "STUDENT" and student.user_id != g.user.id:
        raise APIError("Access denied", 403)
    if g.user.role == "COACH" and student.coach_id != g.user.coach.id:
        raise APIError("Student is not assigned to you", 403)
    return student


def scoped_students():
    query = select(Student)
    if g.user.role == "STUDENT":
        query = query.where(Student.user_id == g.user.id)
    elif g.user.role == "COACH":
        query = query.where(Student.coach_id == g.user.coach.id)
    return query


def student_ids():
    return [s.id for s in db.session.scalars(scoped_students())]


def profile(record):
    user = record.user
    data = {
        "id": record.id,
        "user_id": user.id,
        "login_id": user.login_id,
        "name": user.name,
        "email": user.email,
        "active": user.active,
        "phone": record.phone,
    }
    if isinstance(record, Student):
        data.update(
            coach_id=record.coach_id,
            coach_name=record.coach.user.name if record.coach else None,
            date_of_birth=record.date_of_birth.isoformat(),
            joined_on=record.joined_on.isoformat(),
            level=record.level,
        )
    else:
        data.update(specialty=record.specialty)
    return data


def update_profile(record, data):
    for key in ("name", "email", "active"):
        if key in data:
            if key == "active":
                if type(data[key]) is not bool:
                    raise APIError("active must be a boolean")
                if (
                    not data[key]
                    and isinstance(record, Coach)
                    and any(s.user.active for s in record.students)
                ):
                    raise APIError(
                        "Reassign or deactivate this coach's students first", 409
                    )
                record.user.active = data[key]
                if not data[key]:
                    db.session.execute(
                        delete(AuthSession).where(AuthSession.user_id == record.user_id)
                    )
            else:
                setattr(
                    record.user,
                    key,
                    email(data[key]) if key == "email" else text(data[key], key, 100),
                )
    if "phone" in data:
        record.phone = text(data["phone"], "phone", 30, empty=True)
    if "password" in data:
        record.user.password_hash = generate_password_hash(password(data["password"]))
        db.session.execute(
            delete(AuthSession).where(AuthSession.user_id == record.user_id)
        )
    if isinstance(record, Coach):
        if "specialty" in data:
            record.specialty = text(data["specialty"], "specialty", 100)
        return
    for key in ("date_of_birth", "joined_on"):
        if key in data:
            value = day(data[key], key)
            if value > academy_today():
                raise APIError(f"{key} cannot be in the future")
            setattr(record, key, value)
    if (
        record.date_of_birth
        and record.joined_on
        and record.date_of_birth >= record.joined_on
    ):
        raise APIError("Birth date must precede joining date")
    if "level" in data:
        record.level = choice(
            data["level"], "level", ("Beginner", "Intermediate", "Advanced")
        )
    if "coach_id" in data:
        if data["coach_id"] is None:
            record.coach_id = None
        else:
            coach = get(Coach, integer(data["coach_id"], "coach_id"))
            if not coach.user.active:
                raise APIError("Cannot assign an inactive coach")
            record.coach_id = coach.id
