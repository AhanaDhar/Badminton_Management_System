"""Run with: streamlit run frontend/app.py (from the project root)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
import streamlit as st
from frontend.client import APIClientError, api
from frontend import views

load_dotenv()
st.set_page_config(page_title="Shuttle Academy", page_icon="🏸", layout="wide")


def login():
    st.title("🏸 Shuttle Academy")
    st.subheader("Your next level starts here")
    st.write("Manage training, follow progress, and keep your academy connected.")
    _, center, _ = st.columns([1, 2, 1])
    with center, st.container(border=True):
        st.subheader("Welcome back")
        role = st.radio(
            "Select your role", ["Admin", "Coach", "Student"], index=2, horizontal=True
        )
        with st.form("login"):
            login_id = st.text_input("Academy ID")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                if role is None:
                    st.error("Select a role before signing in.")
                else:
                    st.session_state.auth = api(
                        "/auth/login",
                        "POST",
                        {
                            "role": role.upper(),
                            "login_id": login_id,
                            "password": password,
                        },
                        authenticated=False,
                    )
                    st.rerun()
    st.caption(
        "Secure access for administrators, coaches, and students. Contact your administrator if you need an account or password reset."
    )


def main():
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))
    if "auth" not in st.session_state:
        login()
        return
    user = api(
        "/auth/me"
    )  # Revalidate role and account state on every Streamlit rerun.
    st.session_state.meta = api("/meta")
    role = user["role"]
    menus = {
        "ADMIN": [
            "Overview",
            "Students",
            "Coaches",
            "Training",
            "Court bookings",
            "Attendance",
            "Performance",
            "Tournaments",
            "Feedback",
            "Fees & payments",
            "Monthly reports",
            "Account",
        ],
        "COACH": [
            "Overview",
            "Students",
            "Training",
            "Attendance",
            "Performance",
            "Tournaments",
            "Feedback",
            "Account",
        ],
        "STUDENT": [
            "Overview",
            "My profile",
            "Training",
            "Attendance",
            "Performance",
            "Tournaments",
            "Feedback",
            "Fees & payments",
            "Account",
        ],
    }
    with st.sidebar:
        st.title("🏸 Shuttle")
        st.caption("ACADEMY MANAGEMENT")
        st.write(f"**{user['name']}**")
        st.caption(role.title() + " · " + user["login_id"])
        page = st.radio(
            "Navigation", menus[role], label_visibility="collapsed", key="navigation"
        )
        st.divider()
        st.caption(
            st.session_state.meta["timezone"]
            + " · "
            + st.session_state.meta["currency"]
        )
        if st.button("Sign out", width="stretch"):
            api("/auth/logout", "POST")
            st.session_state.clear()
            st.rerun()
    st.title(page)
    st.caption("Train with purpose. Measure your progress.")
    dispatch = {
        "Overview": lambda: views.overview(role),
        "Students": lambda: views.people("students", role),
        "Coaches": lambda: views.people("coaches", role),
        "My profile": views.profile,
        "Training": lambda: views.schedules(role),
        "Court bookings": views.bookings,
        "Attendance": lambda: views.attendance(role),
        "Performance": lambda: views.progress(role),
        "Tournaments": lambda: views.tournaments(role),
        "Feedback": lambda: views.feedback(role),
        "Fees & payments": lambda: views.finance(role),
        "Monthly reports": views.reports,
        "Account": views.account,
    }
    dispatch[page]()


try:
    main()
except APIClientError as error:
    st.error(str(error))
    st.info("Correct the input or use the sidebar to continue.")
