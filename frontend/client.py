"""The frontend never opens a database connection."""

import os
import requests
import streamlit as st


class APIClientError(Exception):
    pass


def api(path, method="GET", data=None, params=None, raw=False, authenticated=True):
    base = os.getenv("API_URL", "http://127.0.0.1:5000/api").rstrip("/")
    headers = {}
    if authenticated and "auth" in st.session_state:
        headers["Authorization"] = "Bearer " + st.session_state.auth["token"]
    try:
        response = requests.request(
            method,
            base + path,
            json=data,
            params=params,
            headers=headers,
            timeout=(5, 20),
        )
    except requests.RequestException as exc:
        raise APIClientError(
            "Cannot reach the academy API. Check that the backend is running."
        ) from exc
    if response.status_code == 401 and authenticated:
        st.session_state.clear()
        st.session_state.flash = "Your session ended. Please sign in again."
        st.rerun()
    if not response.ok:
        try:
            message = response.json().get("error", "Request failed")
        except ValueError:
            message = "The server returned an unexpected response"
        raise APIClientError(message)
    if raw:
        return response.content
    return response.json() if response.status_code != 204 else None


def save(path, data=None, method="POST"):
    api(path, method, data)
    st.session_state.flash = "Changes saved successfully."
    st.rerun()
