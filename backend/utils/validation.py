"""Reject unknown fields and normalize JSON values before database writes."""

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from flask import request


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def payload(allowed, required=()):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("A JSON object is required")
    unknown = set(data) - set(allowed)
    if unknown:
        raise APIError("Unknown fields: " + ", ".join(sorted(unknown)))
    missing = set(required) - set(data)
    if missing:
        raise APIError("Missing fields: " + ", ".join(sorted(missing)))
    return data


def text(value, field, limit=200, empty=False):
    if (
        not isinstance(value, str)
        or len(value.strip()) > limit
        or (not empty and not value.strip())
    ):
        raise APIError(f"{field} must be {'0' if empty else '1'}–{limit} characters")
    return value.strip()


def integer(value, field, minimum=1, maximum=2147483647):
    if type(value) is not int or not minimum <= value <= maximum:
        raise APIError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def choice(value, field, values):
    if value not in values:
        raise APIError(f"{field} must be one of: {', '.join(values)}")
    return value


def day(value, field):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise APIError(f"{field} must be YYYY-MM-DD") from None


def instant(value, field):
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        raise APIError(f"{field} must be an ISO datetime with a timezone") from None


def money(value, field="amount"):
    try:
        if isinstance(value, bool):
            raise ValueError
        result = Decimal(str(value))
        if (
            not result.is_finite()
            or result <= 0
            or result > Decimal("99999999.99")
            or result != result.quantize(Decimal(".01"))
        ):
            raise ValueError
        return result.quantize(Decimal(".01"))
    except (InvalidOperation, ValueError, TypeError):
        raise APIError(
            f"{field} must be positive, at most 99999999.99, with at most two decimal places"
        ) from None


def password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise APIError("Password must contain 12–128 characters")
    return value


def email(value):
    value = text(value, "email", 120)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise APIError("Invalid email address")
    return value
