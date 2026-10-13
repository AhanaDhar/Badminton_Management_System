from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo
import pandas as pd
from flask import Blueprint, Response, g, jsonify, request
from ..services.analytics import dashboard, monthly_report
from ..utils.security import require
from ..utils.validation import APIError

bp = Blueprint("analytics", __name__, url_prefix="/api")


@bp.get("/analytics")
@require()
def analytics():
    return jsonify(dashboard(g.user.role))


@bp.get("/reports/monthly")
@require("ADMIN")
def monthly():
    month = request.args.get("month", "")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise APIError("month must be YYYY-MM")
    year, number = map(int, month.split("-"))
    if not 2000 <= year <= 2100 or not 1 <= number <= 12:
        raise APIError("Invalid month (years 2000–2100)")
    report = monthly_report(year, number)
    output_format = request.args.get("format", "json")
    if output_format not in ("json", "csv"):
        raise APIError("format must be json or csv")
    if output_format == "csv":
        columns = [
            "student_id",
            "name",
            "level",
            "scheduled",
            "present",
            "absent",
            "excused",
            "unmarked",
            "attendance_percentage",
            "fees_due_this_month",
            "collected_this_month",
            "outstanding_at_month_end",
        ]
        frame = pd.DataFrame(report["students"], columns=columns)
        # Prevent spreadsheet formula injection in user-entered text.
        for column in ("name", "level"):
            frame[column] = frame[column].map(
                lambda v: "'" + v
                if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@"))
                else v
            )
        return Response(
            frame.to_csv(index=False),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="academy-{month}.csv"'
            },
        )
    return jsonify(report)


@bp.get("/meta")
@require()
def meta():
    import os

    zone = os.getenv("ACADEMY_TIMEZONE", "Asia/Kolkata")
    now = datetime.now(timezone.utc)
    return jsonify(
        timezone=zone,
        currency=os.getenv("ACADEMY_CURRENCY", "INR"),
        today=now.astimezone(ZoneInfo(zone)).date().isoformat(),
        server_time=now.isoformat(),
    )
