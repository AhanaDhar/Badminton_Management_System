from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import streamlit as st
from .client import api, save

METRICS = ["agility", "endurance", "footwork", "technique"]
COLORS = ["#079B80", "#476CDA", "#E0A03B", "#A36DD0"]


def today():
    return date.fromisoformat(st.session_state.meta["today"])


def currency(value):
    return f"{st.session_state.meta['currency']} {Decimal(str(value)):,.2f}"


def options(rows, key="name", blank=False):
    mapping = {r["id"]: f"{r.get(key, 'Record')} · #{r['id']}" for r in rows}
    if blank:
        mapping = {None: "Unassigned", **mapping}
    return mapping


def picker(label, mapping, default=None, key=None):
    ids = list(mapping)
    if not ids:
        st.info(f"No available {label.lower()} records. Add them first.")
        st.stop()
    return st.selectbox(
        label,
        ids,
        index=ids.index(default) if default in ids else 0,
        format_func=lambda i: mapping[i],
        key=key,
    )


def table(rows, key, filters=()):
    if not rows:
        st.info("No records yet.")
        return
    frame = pd.DataFrame(rows)
    search = st.text_input(
        "Search records", key=key + "_search", placeholder="Name, ID, date, or keyword"
    )
    if search:
        frame = frame[
            frame.astype(str)
            .apply(lambda c: c.str.contains(search, case=False, regex=False))
            .any(axis=1)
        ]
    for column in filters:
        if column in frame:
            values = sorted(frame[column].dropna().astype(str).unique())
            selected = st.multiselect(
                column.replace("_", " ").title(), values, key=key + "_" + column
            )
            if selected:
                frame = frame[frame[column].astype(str).isin(selected)]
    st.caption(f"{len(frame)} records")
    st.dataframe(frame, width="stretch", hide_index=True)


def editor(rows, resource, display="name", can_delete=True):
    actions = ["Create", "Edit"] + (["Delete"] if can_delete else [])
    mode = (
        st.radio("Action", actions, index=0, horizontal=True, key=resource + "_mode")
        or "Create"
    )
    record = {}
    if mode != "Create":
        identifier = picker("Record", options(rows, display), key=resource + "_record")
        record = next(r for r in rows if r["id"] == identifier)
    return mode, record


def delete_form(resource, record):
    st.warning(
        "Deletion is permanent. Records linked to academic or payment history are protected."
    )
    with st.form(resource + "_delete"):
        confirm = st.checkbox(f"Confirm deletion of record #{record['id']}")
        if st.form_submit_button("Delete record", type="primary"):
            if confirm:
                save(f"/{resource}/{record['id']}", method="DELETE")
            else:
                st.error("Select the confirmation checkbox to delete.")


def submit(resource, mode, record, data):
    path = f"/{resource}/{record['id']}" if mode == "Edit" else f"/{resource}"
    save(path, data, "PATCH" if mode == "Edit" else "POST")


def overview(role):
    data = api("/analytics")
    st.subheader(
        "Academy at a glance" if role == "ADMIN" else "Your training at a glance"
    )
    a, b, c, d = st.columns(4)
    a.metric(
        "Active students" if role != "STUDENT" else "Tournament entries",
        data["active_students"] if role != "STUDENT" else data["tournament_entries"],
    )
    b.metric(
        "Attendance",
        "—"
        if data["attendance_percentage"] is None
        else f"{data['attendance_percentage']}%",
    )
    c.metric(
        "Outstanding fees" if role != "COACH" else "Achievements",
        currency(data["outstanding"]) if role != "COACH" else data["achievements"],
    )
    d.metric(
        "Coaches" if role == "ADMIN" else "Unmarked attendance",
        data["coaches"] if role == "ADMIN" else data["unmarked_attendance"],
    )
    st.caption(
        "Attendance = present ÷ past enrolled sessions, excluding excused sessions. Unmarked past sessions remain in the denominator."
    )
    left, right = st.columns([2, 1])
    with left, st.container(border=True):
        st.subheader("Performance trend")
        frame = pd.DataFrame(data["performance_monthly"])
        if not frame.empty:
            st.plotly_chart(
                px.line(
                    frame,
                    x="month",
                    y=METRICS,
                    markers=True,
                    color_discrete_sequence=COLORS,
                    range_y=[0, 100],
                    labels={
                        "value": "Score / 100",
                        "month": "Month",
                        "variable": "Metric",
                    },
                ),
                use_container_width=True,
            )
        else:
            st.info("Performance records will appear here as training progresses.")
        st.caption(
            "Monthly mean of recorded scores across the students visible to your role."
        )
    with right, st.container(border=True):
        if role == "ADMIN":
            st.subheader("Training levels")
            frame = pd.DataFrame(data["level_distribution"])
            if not frame.empty:
                st.plotly_chart(
                    px.pie(
                        frame,
                        names="level",
                        values="count",
                        hole=0.65,
                        color_discrete_sequence=COLORS,
                    ),
                    use_container_width=True,
                )
        else:
            st.subheader("Attendance breakdown")
            rows = data["attendance_by_student"]
            totals = {
                k: sum(r[k] for r in rows)
                for k in ("present", "absent", "excused", "unmarked")
            }
            if sum(totals.values()):
                st.plotly_chart(
                    px.pie(
                        names=list(totals),
                        values=list(totals.values()),
                        hole=0.65,
                        color_discrete_sequence=COLORS,
                    ),
                    use_container_width=True,
                )
    if role != "COACH":
        frame = pd.DataFrame(data["collections_monthly"])
        if not frame.empty:
            st.subheader("Payment collections")
            st.plotly_chart(
                px.bar(
                    frame,
                    x="month",
                    y="amount",
                    color_discrete_sequence=COLORS,
                    labels={
                        "amount": st.session_state.meta["currency"],
                        "month": "Month",
                    },
                ),
                use_container_width=True,
            )
    st.subheader("Attendance by student")
    table(data["attendance_by_student"], "overview")


def people(resource, role):
    rows = api("/" + resource)
    st.subheader("Student directory" if resource == "students" else "Coaching team")
    table(
        rows, resource, ("level", "active") if resource == "students" else ("active",)
    )
    if role != "ADMIN":
        return
    st.divider()
    st.subheader("Manage " + resource)
    mode, record = editor(rows, resource)
    if mode == "Delete":
        delete_form(resource, record)
        return
    coaches = options(api("/coaches"), blank=True) if resource == "students" else {}
    with st.form(resource + "_form"):
        col1, col2 = st.columns(2)
        with col1:
            login_id = st.text_input(
                "Academy ID", value=record.get("login_id", ""), disabled=mode == "Edit"
            )
            name = st.text_input("Full name", value=record.get("name", ""))
            email = st.text_input("Email", value=record.get("email", ""))
            password = st.text_input(
                "Password (12–128 characters)"
                if mode == "Create"
                else "Reset password (leave blank to keep)",
                type="password",
            )
        with col2:
            phone = st.text_input("Phone", value=record.get("phone", ""))
            active = st.checkbox("Active account", value=record.get("active", True))
            if resource == "students":
                dob = st.date_input(
                    "Date of birth",
                    value=date.fromisoformat(record.get("date_of_birth", "2010-05-15")),
                    min_value=date(1920, 1, 1),
                    max_value=today(),
                )
                joined = st.date_input(
                    "Joined on",
                    value=date.fromisoformat(
                        record.get("joined_on", today().isoformat())
                    ),
                    min_value=date(1920, 1, 1),
                    max_value=today(),
                )
                levels = ["Beginner", "Intermediate", "Advanced"]
                level = st.selectbox(
                    "Training level",
                    levels,
                    index=levels.index(record.get("level", "Beginner")),
                )
                coach = picker("Assigned coach", coaches, record.get("coach_id"))
            else:
                specialty = st.text_input(
                    "Specialty", value=record.get("specialty", "")
                )
        if st.form_submit_button(
            "Save " + ("student" if resource == "students" else "coach"), type="primary"
        ):
            data = {"name": name, "email": email, "phone": phone, "active": active}
            if mode == "Create":
                data.update(login_id=login_id, password=password)
            elif password:
                data["password"] = password
            if resource == "students":
                data.update(
                    date_of_birth=dob.isoformat(),
                    joined_on=joined.isoformat(),
                    level=level,
                    coach_id=coach,
                )
            else:
                data["specialty"] = specialty
            submit(resource, mode, record, data)
    st.caption(
        "To preserve linked history, deactivate an account instead of deleting it. Reassign students before deactivating a coach."
    )


def profile():
    student = api("/students")[0]
    st.subheader("Your profile")
    with st.container(border=True):
        st.title(student["name"])
        st.caption(student["login_id"] + " · " + student["level"])
        a, b = st.columns(2)
        a.write(f"**Coach:** {student['coach_name'] or 'Unassigned'}")
        a.write(f"**Email:** {student['email']}")
        a.write(f"**Phone:** {student['phone'] or '—'}")
        b.write(f"**Date of birth:** {student['date_of_birth']}")
        b.write(f"**Joined:** {student['joined_on']}")
    st.info("Contact the academy administrator to update profile details.")


def schedules(role):
    rows = api("/sessions")
    st.subheader("Training calendar")
    if rows:
        frame = pd.DataFrame(rows)
        frame["start"] = pd.to_datetime(frame.starts_at, utc=True).dt.tz_convert(
            st.session_state.meta["timezone"]
        )
        frame["end"] = pd.to_datetime(frame.ends_at, utc=True).dt.tz_convert(
            st.session_state.meta["timezone"]
        )
        st.plotly_chart(
            px.timeline(
                frame,
                x_start="start",
                x_end="end",
                y="court_name",
                color="coach_name",
                hover_name="title",
                color_discrete_sequence=COLORS,
            ),
            use_container_width=True,
        )
    st.caption("Calendar uses the academy timezone; table timestamps use UTC (Z).")
    table(rows, "sessions", ("coach_name",))
    if role == "STUDENT":
        return
    st.divider()
    mode, record = editor(rows, "sessions", "title")
    if mode == "Delete":
        delete_form("sessions", record)
        return
    coaches = api("/coaches")
    coach_id = picker(
        "Session coach",
        options([c for c in coaches if c["active"]]),
        record.get("coach_id"),
        key="session_coach",
    )
    students = [
        s for s in api("/students") if s["coach_id"] == coach_id and s["active"]
    ]
    names = options(students)
    courts = options(api("/courts"))
    zone = ZoneInfo(st.session_state.meta["timezone"])
    start = (
        datetime.fromisoformat(record["starts_at"].replace("Z", "+00:00")).astimezone(
            zone
        )
        if record
        else datetime.combine(today() + timedelta(days=1), time(16), zone)
    )
    end = (
        datetime.fromisoformat(record["ends_at"].replace("Z", "+00:00")).astimezone(
            zone
        )
        if record
        else start + timedelta(hours=1)
    )
    with st.form("session_form"):
        title = st.text_input("Training title", value=record.get("title", ""))
        focus = st.text_input("Training focus", value=record.get("focus", ""))
        enrolled = st.multiselect(
            "Enrolled students",
            list(names),
            default=[i for i in record.get("student_ids", []) if i in names],
            format_func=lambda i: names[i],
        )
        court = picker("Court", courts, record.get("court_id"))
        c1, c2 = st.columns(2)
        start_day = c1.date_input("Start date", value=start.date())
        start_time = c1.time_input(
            "Start time", value=start.time().replace(tzinfo=None)
        )
        end_day = c2.date_input("End date", value=end.date())
        end_time = c2.time_input("End time", value=end.time().replace(tzinfo=None))
        if st.form_submit_button("Save training session", type="primary"):
            data = {
                "coach_id": coach_id,
                "title": title,
                "focus": focus,
                "student_ids": enrolled,
            }
            proposed_start = (
                datetime.combine(start_day, start_time, zone)
                .astimezone(timezone.utc)
                .isoformat()
            )
            proposed_end = (
                datetime.combine(end_day, end_time, zone)
                .astimezone(timezone.utc)
                .isoformat()
            )
            if mode == "Create" or court != record["court_id"]:
                data["court_id"] = court
            if mode == "Create" or datetime.fromisoformat(proposed_start) != start:
                data["starts_at"] = proposed_start
            if mode == "Create" or datetime.fromisoformat(proposed_end) != end:
                data["ends_at"] = proposed_end
            submit("sessions", mode, record, data)
    st.caption(
        "Court overlaps and simultaneous coach sessions are blocked by the API. Timing and enrollment lock once attendance is recorded."
    )


def bookings():
    with st.expander("Court inventory"):
        courts = api("/courts")
        table(courts, "court_inventory")
        mode, record = editor(courts, "courts")
        if mode == "Delete":
            delete_form("courts", record)
        else:
            with st.form("court_form"):
                name = st.text_input("Court name", value=record.get("name", ""))
                if st.form_submit_button("Save court", type="primary"):
                    submit("courts", mode, record, {"name": name})
    rows = api("/bookings")
    st.subheader("Court bookings")
    table(rows, "bookings", ("court_name",))
    session_booking_ids = {s["booking_id"] for s in api("/sessions")}
    mode, record = editor(
        [r for r in rows if r["id"] not in session_booking_ids], "bookings", "purpose"
    )
    if mode == "Delete":
        delete_form("bookings", record)
        return
    courts = options(api("/courts"))
    zone = ZoneInfo(st.session_state.meta["timezone"])
    start = (
        datetime.fromisoformat(record["starts_at"].replace("Z", "+00:00")).astimezone(
            zone
        )
        if record
        else datetime.combine(today() + timedelta(days=1), time(9), zone)
    )
    end = (
        datetime.fromisoformat(record["ends_at"].replace("Z", "+00:00")).astimezone(
            zone
        )
        if record
        else start + timedelta(hours=1)
    )
    with st.form("booking_form"):
        court = picker("Court", courts, record.get("court_id"))
        purpose = st.text_input("Purpose", value=record.get("purpose", ""))
        a, b = st.columns(2)
        start_day, start_time = (
            a.date_input("Start date", start.date()),
            a.time_input("Start time", start.time().replace(tzinfo=None)),
        )
        end_day, end_time = (
            b.date_input("End date", end.date()),
            b.time_input("End time", end.time().replace(tzinfo=None)),
        )
        if st.form_submit_button("Save booking", type="primary"):
            submit(
                "bookings",
                mode,
                record,
                {
                    "court_id": court,
                    "purpose": purpose,
                    "starts_at": datetime.combine(
                        start_day, start_time, zone
                    ).isoformat(),
                    "ends_at": datetime.combine(end_day, end_time, zone).isoformat(),
                },
            )
    st.caption("Training reservations are edited from the Training page.")


def attendance(role):
    st.subheader("Attendance register")
    data = api("/analytics")
    table(data["attendance_by_student"], "attendance_summary")
    table(api("/attendance"), "attendance", ("status",))
    st.caption(
        "Excused sessions are excluded from the percentage; past unmarked sessions count toward the denominator."
    )
    if role == "STUDENT":
        return
    now = datetime.fromisoformat(st.session_state.meta["server_time"])
    sessions = [
        s
        for s in api("/sessions")
        if datetime.fromisoformat(s["starts_at"].replace("Z", "+00:00")) <= now
    ]
    identifier = picker(
        "Training session", options(sessions, "title"), key="attendance_session"
    )
    session = next(s for s in sessions if s["id"] == identifier)
    students = [s for s in api("/students") if s["id"] in session["student_ids"]]
    with st.form("attendance_form"):
        student = picker("Student", options(students))
        status = st.radio("Status", ["present", "absent", "excused"], horizontal=True)
        if st.form_submit_button("Save attendance", type="primary"):
            save(
                "/attendance",
                {"session_id": identifier, "student_id": student, "status": status},
                "PUT",
            )


def progress(role):
    st.subheader("Player development")
    students = api("/students")
    identifier = picker("Student", options(students), key="progress_student")
    rows = [r for r in api("/performance") if r["student_id"] == identifier]
    if rows:
        frame = pd.DataFrame(rows).sort_values(["recorded_on", "id"])
        st.plotly_chart(
            px.line(
                frame,
                x="recorded_on",
                y=METRICS,
                markers=True,
                range_y=[0, 100],
                color_discrete_sequence=COLORS,
                labels={
                    "value": "Score / 100",
                    "recorded_on": "Recorded on",
                    "variable": "Metric",
                },
            ),
            use_container_width=True,
        )
        first, last = frame.iloc[0], frame.iloc[-1]
        for column, metric in zip(st.columns(4), METRICS):
            column.metric(
                metric.title(),
                int(last[metric]),
                f"{int(last[metric]) - int(first[metric]):+d} pts since first record",
            )
    st.caption(
        "All metrics use a 0–100 coach assessment scale, where higher scores indicate stronger performance."
    )
    table(rows, "performance")
    if role == "STUDENT":
        return
    mode, record = editor(rows, "performance", "recorded_on")
    if mode == "Delete":
        delete_form("performance", record)
        return
    with st.form("performance_form"):
        recorded_on = st.date_input(
            "Recorded on",
            date.fromisoformat(record.get("recorded_on", today().isoformat())),
            max_value=today(),
        )
        scores = {m: st.slider(m.title(), 0, 100, record.get(m, 50)) for m in METRICS}
        notes = st.text_area("Assessment notes", value=record.get("notes", ""))
        if st.form_submit_button("Save performance", type="primary"):
            submit(
                "performance",
                mode,
                record,
                {
                    "student_id": identifier,
                    "recorded_on": recorded_on.isoformat(),
                    "notes": notes,
                    **scores,
                },
            )


def feedback(role):
    st.subheader("Coach feedback")
    rows = api("/feedback")
    table(rows, "feedback")
    for row in reversed(rows[-10:]):
        with st.container(border=True):
            st.write(
                f"**{row['student_name']}** · {row['recorded_on']} · {row['coach_name']}"
            )
            st.text(row["message"])
    if role == "STUDENT":
        return
    mode, record = editor(rows, "feedback", "student_name")
    if mode == "Delete":
        delete_form("feedback", record)
        return
    with st.form("feedback_form"):
        student = picker("Student", options(api("/students")), record.get("student_id"))
        recorded_on = st.date_input(
            "Feedback date",
            date.fromisoformat(record.get("recorded_on", today().isoformat())),
            max_value=today(),
        )
        message = st.text_area("Individual feedback", value=record.get("message", ""))
        if st.form_submit_button("Save feedback", type="primary"):
            submit(
                "feedback",
                mode,
                record,
                {
                    "student_id": student,
                    "recorded_on": recorded_on.isoformat(),
                    "message": message,
                },
            )


def tournaments(role):
    st.subheader("Tournaments & achievements")
    events = api("/tournaments")
    results = api("/results")
    st.metric("Achievements", sum(bool(r["achievement"]) for r in results))
    table(events, "tournaments")
    table(results, "results", ("category", "result"))
    if role == "STUDENT":
        return
    event_tab, result_tab = st.tabs(["Tournament events", "Student results"])
    with event_tab:
        mode, record = (
            editor(events, "tournaments", can_delete=role == "ADMIN")
            if role == "ADMIN"
            else ("Create", {})
        )
        if mode == "Delete":
            delete_form("tournaments", record)
        else:
            with st.form("tournament_form"):
                name = st.text_input("Tournament name", value=record.get("name", ""))
                location = st.text_input("Location", value=record.get("location", ""))
                event_date = st.date_input(
                    "Event date",
                    date.fromisoformat(record.get("event_date", today().isoformat())),
                )
                if st.form_submit_button("Save tournament", type="primary"):
                    submit(
                        "tournaments",
                        mode,
                        record,
                        {
                            "name": name,
                            "location": location,
                            "event_date": event_date.isoformat(),
                        },
                    )
    with result_tab:
        mode, record = editor(results, "results", "student_name")
        if mode == "Delete":
            delete_form("results", record)
        elif events:
            with st.form("result_form"):
                event = picker(
                    "Tournament", options(events), record.get("tournament_id")
                )
                student = picker(
                    "Student", options(api("/students")), record.get("student_id")
                )
                category = st.text_input(
                    "Category", value=record.get("category", "U17 Singles")
                )
                result = st.text_input(
                    "Result / participation",
                    value=record.get("result", "Participating"),
                )
                achievement = st.text_input(
                    "Achievement (optional)", value=record.get("achievement", "")
                )
                if st.form_submit_button("Save result", type="primary"):
                    submit(
                        "results",
                        mode,
                        record,
                        {
                            "student_id": student,
                            "tournament_id": event,
                            "category": category,
                            "result": result,
                            "achievement": achievement,
                        },
                    )
        else:
            st.info("Create a tournament before recording a result.")


def finance(role):
    fees, payments = api("/fees"), api("/payments")
    st.subheader("Fees & payments")
    a, b, c = st.columns(3)
    a.metric("Fees billed", currency(sum(Decimal(f["amount"]) for f in fees)))
    b.metric("Collected", currency(sum(Decimal(p["amount"]) for p in payments)))
    c.metric("Outstanding", currency(sum(Decimal(f["outstanding"]) for f in fees)))
    st.write("**Fee ledger**")
    table(fees, "fees", ("student_name",))
    st.write("**Payment history**")
    table(payments, "payments", ("method",))
    if role == "STUDENT":
        return
    fee_tab, payment_tab = st.tabs(["Manage fees", "Record payment"])
    with fee_tab:
        mode, record = editor(fees, "fees", "description")
        if mode == "Delete":
            delete_form("fees", record)
        else:
            with st.form("fee_form"):
                student = picker(
                    "Student", options(api("/students")), record.get("student_id")
                )
                description = st.text_input(
                    "Description",
                    value=record.get("description", "Monthly training fee"),
                )
                amount = st.number_input(
                    "Fee amount",
                    min_value=0.01,
                    max_value=99999999.99,
                    value=float(record.get("amount", "2500.00")),
                    step=100.0,
                    format="%.2f",
                )
                due_date = st.date_input(
                    "Due date",
                    date.fromisoformat(record.get("due_date", today().isoformat())),
                )
                if st.form_submit_button("Save fee", type="primary"):
                    submit(
                        "fees",
                        mode,
                        record,
                        {
                            "student_id": student,
                            "description": description,
                            "amount": f"{amount:.2f}",
                            "due_date": due_date.isoformat(),
                        },
                    )
    with payment_tab:
        unpaid = [f for f in fees if Decimal(f["outstanding"]) > 0]
        if not unpaid:
            st.success("All fees are settled.")
            return
        mapping = {
            f[
                "id"
            ]: f"{f['student_name']} · {f['description']} · {currency(f['outstanding'])} remaining"
            for f in unpaid
        }
        identifier = picker("Fee to pay", mapping, key="payment_fee")
        fee = next(f for f in unpaid if f["id"] == identifier)
        with st.form("payment_form"):
            amount = st.number_input(
                "Payment amount",
                min_value=0.01,
                max_value=float(fee["outstanding"]),
                value=float(fee["outstanding"]),
                format="%.2f",
            )
            paid_on = st.date_input(
                "Paid on",
                today(),
                min_value=date.fromisoformat(fee["created_on"]),
                max_value=today(),
            )
            method = st.selectbox("Payment method", ["cash", "bank", "card", "upi"])
            reference = st.text_input("Unique receipt / transaction reference")
            if st.form_submit_button("Record payment", type="primary"):
                save(
                    "/payments",
                    {
                        "fee_id": identifier,
                        "amount": f"{amount:.2f}",
                        "paid_on": paid_on.isoformat(),
                        "method": method,
                        "reference": reference,
                    },
                )
        st.caption(
            "This records payments received externally. Payment history is immutable; duplicate references and overpayments are rejected."
        )


def reports():
    st.subheader("Monthly academy report")
    month = st.date_input(
        "Choose reporting month",
        today().replace(day=1),
        min_value=date(2000, 1, 1),
        max_value=date(2100, 12, 31),
    ).strftime("%Y-%m")
    data = api("/reports/monthly", params={"month": month})
    a, b = st.columns(2)
    a.metric("Collections in month", currency(data["collected"]))
    b.metric("Outstanding at month end", currency(data["outstanding"]))
    table(data["students"], "report")
    st.write("**Average performance scores this month**", data["performance_averages"])
    csv = api("/reports/monthly", params={"month": month, "format": "csv"}, raw=True)
    st.download_button(
        "Download monthly CSV",
        csv,
        file_name=f"academy-{month}.csv",
        mime="text/csv",
        type="primary",
    )
    st.caption(
        "Month-end balances use recorded payment dates and current fee amounts; subsequent fee edits affect regenerated historical reports."
    )


def account():
    st.subheader("Account security")
    with st.form("password_form"):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password (12–128 characters)", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Change password", type="primary"):
            if new != confirm:
                st.error("Passwords do not match.")
            else:
                api(
                    "/auth/password",
                    "POST",
                    {"current_password": current, "new_password": new},
                )
                st.session_state.clear()
                st.session_state.flash = (
                    "Password changed. Sign in with your new password."
                )
                st.rerun()
