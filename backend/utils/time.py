import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def academy_today():
    return (
        datetime.now(timezone.utc)
        .astimezone(ZoneInfo(os.getenv("ACADEMY_TIMEZONE", "Asia/Kolkata")))
        .date()
    )
