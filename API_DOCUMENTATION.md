# REST API reference

Base URL: `http://127.0.0.1:5000/api` for native development. Compose uses `http://backend:5000/api` between containers. Routes accept JSON; use `Content-Type: application/json`. Protected requests need `Authorization: Bearer <token>`.

Role abbreviations: **A** Admin, **C** Coach, **S** Student. A role being allowed does not waive row-level restrictions. A coach sees currently assigned students; a student sees only their own records. Session access follows the session's coach and explicit student enrollment. Coaches never access fees/payment history.

## Conventions

- Create: HTTP 201 and the created object. Read/update: HTTP 200 and JSON. Delete: HTTP 204 with no body. Lists return JSON arrays ordered by their documented timestamp or ID.
- Body fields not listed below are rejected. POST requires the fields marked required; PATCH accepts a subset unless stated otherwise. There is no public arbitrary SQL, account registration, or role-changing endpoint.
- IDs in URL paths are integer profile/record IDs. `login_id` is the separate human-readable academy ID, case-normalized to uppercase.
- Dates: `YYYY-MM-DD`. Booking datetimes: ISO 8601 with an explicit timezone, such as `2026-11-01T16:00:00+05:30`. Responses use UTC `Z`. Money: decimal strings such as `"2500.00"`; requests may use JSON numbers but strings are preferred. Scores: integers 0–100.
- Profile responses include `id`, `user_id`, `login_id`, `name`, `email`, `active`, `phone`, plus student/coach attributes. Password/token hashes are never returned.
- There are no individual GET endpoints except `/students/{id}`. Lists are role-scoped; frontend table search/filtering operates on those scoped results. Pagination is not included in this single-academy version.
- Maximum JSON request size: 64 KiB.

Errors have the shape `{"error":"Explanation"}`. HTTP 400 = invalid input/business rule, 401 = missing/expired/invalid authentication, 403 = unauthorized role/record, 404 = missing record/route, 409 = duplicate/conflict/protected history, 413 = oversized request, 429 = failed-login limit, 500 = unexpected server error. Error responses contain no credentials or internal traceback.

## Authentication and system endpoints

| Method | Path | Access | Request/response |
|---|---|---|---|
| GET | `/health` | Public | Database connectivity check; `{"status":"ok"}` |
| POST | `/auth/login` | Public | Required `role`, `login_id`, `password`; returns opaque `token`, `expires_at`, and `user` identity |
| GET | `/auth/me` | A/C/S | Returns `id`, `login_id`, `name`, `role`, nullable `student_id`, nullable `coach_id` |
| POST | `/auth/logout` | A/C/S | Revokes current token; `{"message":"Logged out"}` |
| POST | `/auth/password` | A/C/S | Required `current_password`, `new_password`; revokes all tokens after success |
| GET | `/meta` | A/C/S | Academy `timezone`, `currency`, local `today`, UTC `server_time` |

`role` must be ADMIN, COACH, or STUDENT and match the account. Password creation/change/reset requires 12–128 characters. Failed login messages are intentionally the same for unknown ID, incorrect password, incorrect role, and inactive account. Five failures per account or thirty per source address in fifteen minutes return 429. Tokens expire after eight hours and are revocable; they are not JWTs.

Login example:

```json
{"role":"STUDENT","login_id":"S001","password":"YOUR_CHOSEN_DEMO_PASSWORD"}
```

Successful response shape:

```json
{
  "token":"opaque_random_token",
  "expires_at":"2026-11-01T12:00:00Z",
  "user":{"id":4,"login_id":"S001","name":"Aarav Mehta","role":"STUDENT","student_id":1,"coach_id":null}
}
```

## Students and coaches

| Method | Path | Access | Behavior |
|---|---|---|---|
| GET | `/students` | A/C/S | All students / currently assigned students / own student profile |
| GET | `/students/{id}` | A/C/S | Same record-level scope; 403 for other students |
| POST | `/students` | A | Creates student and hashed-password account atomically |
| PATCH | `/students/{id}` | A | Updates profile, assignment, active state; optional password reset revokes tokens |
| DELETE | `/students/{id}` | A | Deletes only if historical dependencies allow it |
| GET | `/coaches` | A/C | All coaches / own coach profile |
| POST | `/coaches` | A | Creates coach and hashed-password account atomically |
| PATCH | `/coaches/{id}` | A | Updates profile/active state; optional password reset |
| DELETE | `/coaches/{id}` | A | Rejects assigned students or historical dependencies |

Student POST required: `login_id`, `name`, `email`, `password`, `date_of_birth`, `joined_on`, `level`. Optional: `phone`, `active`, `coach_id` (null for unassigned). Coach POST required: `login_id`, `name`, `email`, `password`, `specialty`. Optional: `phone`, `active`.

PATCH allows the same profile fields except immutable `login_id`. `active` must be a JSON boolean. Birth/joining dates cannot be future and birth must precede joining. `level` is Beginner/Intermediate/Advanced. `coach_id` must identify an active coach. Account IDs accept letters, numbers, underscores and hyphens. Email format is validated; emails are not required to be unique.

A coach's active students must first be reassigned/deactivated before the coach is deactivated. Deactivation immediately revokes tokens. Historical dependencies block physical deletion; PATCH `active:false` preserves history.

Student creation example:

```json
{
  "login_id":"S007", "name":"New Student", "email":"student7@example.com",
  "password":"A_PASSWORD_YOU_CHOOSE", "date_of_birth":"2011-07-09",
  "joined_on":"2026-10-01", "level":"Beginner", "coach_id":1,
  "phone":"+91 90000 03007", "active":true
}
```

## Courts, bookings, sessions, attendance

| Method | Path | Access | Behavior |
|---|---|---|---|
| GET | `/courts` | A/C | Lists court inventory |
| POST | `/courts` | A | Creates court; required `name` |
| PATCH | `/courts/{id}` | A | Renames court; required `name` |
| DELETE | `/courts/{id}` | A | Rejects deletion when bookings reference it |
| GET | `/bookings` | A/C | Shared court availability; coach responses omit booking `created_by` |
| POST | `/bookings` | A | Creates standalone reservation |
| PATCH | `/bookings/{id}` | A | Edits standalone reservation; training bookings must use `/sessions` |
| DELETE | `/bookings/{id}` | A | Deletes standalone reservation; referenced training bookings are protected |
| GET | `/sessions` | A/C/S | All / own-coach / own enrolled sessions, sorted by start |
| POST | `/sessions` | A/C | Creates session, reservation, and roster atomically |
| PATCH | `/sessions/{id}` | A/C | Edits own/any session, subject to history rules |
| DELETE | `/sessions/{id}` | A/C | Deletes own/any session plus booking if no attendance exists |
| GET | `/attendance` | A/C/S | Attendance marks for visible students |
| PUT | `/attendance` | A/C | Upserts one enrollment's current attendance mark |

Booking POST fields, all required: `court_id`, `starts_at`, `ends_at`, `purpose`. PATCH accepts a subset. Duration must be positive and at most eight hours; creation/moving into the past is forbidden. Existing past booking purpose may be corrected without moving it. Overlapping intervals on a court return 409; an end equal to the next start is valid.

Session POST fields, all required: `coach_id`, `title`, `focus`, `court_id`, `starts_at`, `ends_at`, `student_ids` (nonempty list of unique integer IDs, at most 100). Every student must be active and assigned to the active session coach. Coaches must use their own `coach_id`. Court conflicts and simultaneous sessions for the same coach return 409. Session coach cannot be changed after creation; recreate a history-free session instead.

Session PATCH accepts a subset of POST fields. Once attendance exists, timing/court/enrollment cannot change and deletion is blocked. Title/focus remain editable. Session responses include court/coach names, booking/timing details, and `student_ids` for Admin/Coach; students do not receive classmates' IDs.

Attendance PUT fields, all required: `session_id`, `student_id`, `status`. Allowed statuses: present/absent/excused. The student must be enrolled and visible to the coach, and the session must already have started. Updating a mark retains one row and updates `marked_by`/`marked_at`. The response includes student/session display fields.

Session example (use a future date and IDs from your database):

```json
{
  "coach_id":1, "court_id":1, "title":"Footwork and match play",
  "focus":"Split step and recovery", "starts_at":"2026-11-01T16:00:00+05:30",
  "ends_at":"2026-11-01T17:00:00+05:30", "student_ids":[1,2,3]
}
```

## Performance, feedback, tournaments/results

| Method | Path | Access | Behavior |
|---|---|---|---|
| GET | `/performance` | A/C/S | Visible students' performance records |
| POST | `/performance` | A/C | Creates dated assessment |
| PATCH | `/performance/{id}` | A/C | Admin or author coach with current student assignment |
| DELETE | `/performance/{id}` | A/C | Same author/student restrictions |
| GET | `/feedback` | A/C/S | Visible students' dated feedback |
| POST | `/feedback` | A/C | Creates feedback |
| PATCH | `/feedback/{id}` | A/C | Admin or author coach with current student assignment |
| DELETE | `/feedback/{id}` | A/C | Same author/student restrictions |
| GET | `/tournaments` | A/C/S | Catalogue for staff; own participation events for students |
| POST | `/tournaments` | A/C | Creates tournament event |
| PATCH | `/tournaments/{id}` | A | Edits tournament event |
| DELETE | `/tournaments/{id}` | A | Rejects deletion while results reference it |
| GET | `/results` | A/C/S | Visible students' participation/results |
| POST | `/results` | A/C | Records participation/result |
| PATCH | `/results/{id}` | A/C | Admin or author coach with current student assignment |
| DELETE | `/results/{id}` | A/C | Same author/student restrictions |

Performance POST required: `student_id`, `recorded_on`, `agility`, `endurance`, `footwork`, `technique`. Optional `notes`. Scores are integer 0–100. Feedback POST required: `student_id`, `recorded_on`, `message`. Assessment and feedback dates cannot be future.

Tournament POST required: `name`, `location`, `event_date`. Results POST required: `student_id`, `tournament_id`, `category`, `result`; optional `achievement` (empty means no recorded achievement). Use `result:"Participating"` for upcoming entries. Each tournament/student/category combination is unique.

PATCH accepts a subset of the corresponding fields. Student ownership cannot change on an existing progress/feedback/result row. The coach author is assigned by Flask rather than trusted from the request. Administrators use a new record's student's current assigned active coach as author; existing records retain their original author. Coaches may view visible students' history but cannot edit/delete another coach's authored records.

## Fees and payments

| Method | Path | Access | Behavior |
|---|---|---|---|
| GET | `/fees` | A/S | All / own charges with paid and outstanding balances |
| POST | `/fees` | A | Creates charge |
| PATCH | `/fees/{id}` | A | Edits charge, subject to paid-balance rules |
| DELETE | `/fees/{id}` | A | Deletes unpaid charge only |
| GET | `/payments` | A/S | All / own payment history, sorted by payment date |
| POST | `/payments` | A | Records an externally received payment |

Fee POST required: `student_id`, `description`, `amount`, `due_date`. Creation date is server-assigned in the academy timezone. PATCH accepts a subset; fee student cannot change and amount cannot drop below total payments.

Payment POST required: `fee_id`, `amount`, `paid_on`, `method`, `reference`. Method is cash/bank/card/upi. Payment date must be between fee creation and today. Amount must not exceed the current balance. References are unique globally and protect against recording a receipt twice. No payment PATCH/DELETE is exposed: payment history is immutable. There is no online payment gateway in this application.

Fee response adds decimal-string `paid` and `outstanding`. Payment response adds `student_id`, `student_name`, and fee `description` to its stored fields.

```json
{"fee_id":1,"amount":"1500.00","paid_on":"2026-10-13","method":"upi","reference":"RECEIPT-20261013-001"}
```

## Analytics and reporting

| Method | Path | Access | Behavior |
|---|---|---|---|
| GET | `/analytics` | A/C/S | Aggregated data for visible students; finances excluded for coaches |
| GET | `/reports/monthly?month=YYYY-MM` | A | Monthly JSON report |
| GET | `/reports/monthly?month=YYYY-MM&format=csv` | A | Downloadable monthly CSV |

Analytics returns student/active-student counts, attendance percentage (nullable), unmarked count, attendance by student, performance rows/monthly averages, tournament entry/achievement counts. Admin also receives coach count/level distribution. Admin/Student receive exact collected/outstanding totals and monthly chart collection data.

Attendance percentage is present / past enrolled sessions, excluding excused sessions. Unmarked past enrollments are included in the denominator and separately counted. A zero denominator returns null. Monthly performance values are means of recorded scores, not automatically measured athletic results.

Reports accept years 2000–2100 and valid months. JSON includes `month`, student report rows, `performance_averages`, exact `collected`, and `outstanding`. Each student row contains scheduled/present/absent/excused/unmarked counts, percentage, fees due that month, collections that month, and outstanding at month end. Session boundaries use the academy timezone. Financial reporting uses business dates and current fee amounts; historical regenerated balances change after fee edits. CSV text is sanitized against spreadsheet formulas.

## Example API interaction

Use your chosen credentials and avoid storing bearer tokens in source control or logs:

```python
import requests
from getpass import getpass

base = "http://127.0.0.1:5000/api"
response = requests.post(base + "/auth/login", json={
    "role": "ADMIN", "login_id": "ADM001", "password": getpass("Password: ")
}, timeout=15)
response.raise_for_status()
headers = {"Authorization": "Bearer " + response.json()["token"]}
response = requests.get(base + "/students", headers=headers, timeout=15)
response.raise_for_status()
print(response.json())
requests.post(base + "/auth/logout", headers=headers, timeout=15).raise_for_status()
```

The example masks the password prompt. Streamlit also uses a masked password input.
