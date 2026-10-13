#badminton_management_system

# Shuttle Academy — Badminton Academy Management System

A working Python application with a **Streamlit frontend**, **Flask REST backend**, **MySQL 8.4**, **SQLAlchemy**, **Pandas**, and **Plotly**. Streamlit communicates with Flask over HTTP and does not access the database. This project does not substitute a static website for the requested stack.

## Features

| Role | Capabilities |
|---|---|
| Admin | Create/edit/delete students and coaches, deactivate accounts, reset passwords, assign coaches, manage training and court reservations, mark attendance, manage progress/feedback/tournaments, issue fees, record payments, review analytics, export monthly CSV reports |
| Coach | View assigned students, create/edit/delete own training sessions, mark enrolled student attendance, record and maintain performance, feedback, tournament results, create tournament events, review improvement charts |
| Student | View own profile, enrolled training, attendance percentage, performance charts, tournament results and achievements, outstanding fees, payment history, coach feedback |

All roles can change their password and sign out. The API applies role and record ownership checks independently of sidebar visibility. Searchable tables, category filters, Streamlit forms, cards, Plotly charts, and success/error messages are included. Styling uses Streamlit's native theme; no custom HTML/CSS/JavaScript frontend is required.

## Prerequisites

- Python **3.12**, pip, and a virtual environment.
- MySQL **8.4** (8.0.16+ supports the required enforced check constraints).
- Alternatively, Docker Engine and Docker Compose v2.
- Two terminals for native startup: one for Flask and one for Streamlit.

Run all commands below from this project's root directory. The credentials in `.env.example` are placeholders, not working accounts.

## Option A: Docker Compose

1. Copy `.env.example` to `.env`. Set `MYSQL_USER=academy`, and set `MYSQL_PASSWORD` and `MYSQL_ROOT_PASSWORD` to different strong passwords. Keep `MYSQL_DATABASE=badminton_academy` unless you intend to rename it. Never commit `.env`.

   ```bash
   cp .env.example .env
   ```

2. Build the Python image and start MySQL. Its named volume preserves data between restarts.

   ```bash
   docker compose build
   docker compose up -d db
   ```

3. Apply the committed migration. Provision either realistic demo data **or** your first production admin; do not run both on the same database. Both commands prompt for a password without printing it. Use at least 12 characters.

   ```bash
   docker compose run --rm backend flask --app backend:create_app db upgrade
   # Development demonstration, on an empty database only:
   docker compose run --rm backend flask --app backend:create_app seed-demo
   # OR: clean production setup with no fictional records:
   docker compose run --rm backend flask --app backend:create_app create-admin
   ```

4. Start both application services.

   ```bash
   docker compose up -d backend frontend
   docker compose logs --tail=50 backend frontend
   ```

5. Open **http://localhost:8501**. The API health endpoint is **http://localhost:5000/api/health**. Choose a role, then enter the corresponding ID and your chosen password.

   Demo IDs: **ADM001** (Admin), **C001/C002** (Coach), **S001–S006** (Student). All demo accounts initially use the password you supplied to `seed-demo`; no default password is bundled. Change passwords from the Account page.

`docker compose down` stops the stack and preserves the database volume. **Do not add `-v` unless you intend to destroy the database.** Database ports are not published; application ports bind only to localhost. Compose constructs the database URL using SQLAlchemy's URL builder, so special characters in database passwords are handled safely. Compose interpolates `.env` variables; quote values containing `$` with single quotes in `.env`.

In a managed cloud build requiring an additional CA certificate, the Dockerfile accepts the optional BuildKit secret `proxy_ca`. Build with `docker build --secret id=proxy_ca,src=/path/to/combined-ca.pem -t badminton-academy .`; preserve proxy settings and TLS verification.

## Option B: Native Python and MySQL

1. Create and activate a virtual environment, then install dependencies.

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   On Windows PowerShell, use `py -3.12 -m venv .venv` and `.venv\Scripts\Activate.ps1`.

2. In a MySQL administrator session, create the database and a dedicated application account. Replace the sample password below. Use `localhost` or the application's actual host instead of `%` wherever possible.

   ```sql
   CREATE DATABASE badminton_academy CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'academy'@'localhost' IDENTIFIED BY 'YOUR_STRONG_DATABASE_PASSWORD';
   GRANT ALL PRIVILEGES ON badminton_academy.* TO 'academy'@'localhost';
   ```

   Schema privileges are needed for migrations. For production, use a separate migration account, then grant the runtime account only SELECT, INSERT, UPDATE, and DELETE on this database.

3. Copy `.env.example` to `.env`. Set `DATABASE_URL` to your real SQLAlchemy connection URL and adjust `API_URL`, `ACADEMY_TIMEZONE` (an IANA zone), and `ACADEMY_CURRENCY` (a display code) as needed.

   ```dotenv
   DATABASE_URL=mysql+pymysql://academy:URL_ENCODED_PASSWORD@127.0.0.1:3306/badminton_academy?charset=utf8mb4
   API_URL=http://127.0.0.1:5000/api
   ACADEMY_TIMEZONE=Asia/Kolkata
   ACADEMY_CURRENCY=INR
   ```

   URL-encode special characters in `DATABASE_URL` passwords. Alternatively, set `DATABASE_URL=` and define `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD`; the backend then constructs the URL safely. Timezone and currency are configurable defaults, not assumptions about your academy.

4. Apply migrations and provision data.

   ```bash
   flask --app backend:create_app db upgrade
   flask --app backend:create_app seed-demo
   # OR, instead of demo data:
   flask --app backend:create_app create-admin
   ```

5. In terminal one, start Flask for local development:

   ```bash
   flask --app backend:create_app run --host=127.0.0.1 --port=5000
   ```

6. In terminal two, activate the same virtual environment and start Streamlit:

   ```bash
   streamlit run frontend/app.py --server.port=8501
   ```

   Visit http://localhost:8501. For a production Linux backend, use `gunicorn --bind 127.0.0.1:5000 --workers 2 'backend:create_app()'` instead of Flask's development server.

## Typical workflows

- **Admin:** create coaches, create students and assign a coach, create a training session with enrolled students, then mark attendance once its start time has passed. Issue fees and record externally received payments with unique transaction references. Export reports from Monthly reports.
- **Coach:** review Students, create an own-coach session with assigned students, update Attendance, add weekly 0–100 performance assessments and feedback, and add tournament participation/results.
- **Student:** select Student at login, review Training, Performance, Feedback, and Fees & payments. Profile corrections are performed by an administrator.

Training creates its court reservation in the same transaction. Standalone reservations are managed from Court bookings. Sessions with attendance cannot have timing/enrollment changed or be deleted. Students/coaches linked to history cannot be deleted; deactivate accounts to preserve that history. Reassign or deactivate a coach's active students before deactivating the coach.

## Automated tests

Fast tests use isolated in-memory SQLite with foreign keys enabled; this is a test convenience, not the deployment database.

```bash
python -m pytest -q
ruff check backend frontend tests
ruff format --check backend frontend tests migrations
```

**MySQL integration tests drop all domain tables after each test. Use only a dedicated disposable database; never point `TEST_DATABASE_URL` at academy data.** Create a separate database and a user with schema privileges, then run:

```bash
TEST_DATABASE_URL='mysql+pymysql://test_user:URL_ENCODED_PASSWORD@127.0.0.1:3306/badminton_test' python -m pytest -q
```

PowerShell: `$env:TEST_DATABASE_URL='mysql+pymysql://.../badminton_test'; python -m pytest -q`.

The suite checks authentication, revocation, role/record authorization, people CRUD, assignments, overlapping reservations, schedules, attendance, academic records, fees/payments, analytics/report semantics, CSV formula safety, demo seeding, and Streamlit page execution. MySQL-specific concurrency tests verify that simultaneous booking/payment requests cannot overlap/overpay. They are deliberately skipped by SQLite.

Streamlit tests execute the actual frontend script and send its requests to the actual Flask test client. They are not browser screenshot or mobile device tests. See `TEST_RESULTS.md` for checks actually performed during delivery.

## Migrations and maintenance

```bash
flask --app backend:create_app db current
flask --app backend:create_app db check
# After an intentional model change, generate and REVIEW a new migration:
flask --app backend:create_app db migrate -m "Describe schema change"
flask --app backend:create_app db upgrade
flask --app backend:create_app cleanup-auth
```

Run `cleanup-auth` daily to remove expired tokens and old login attempts. MySQL DDL may auto-commit, so back up the database and test migrations before upgrading production. Do not edit an already-applied migration.

## Security and operational notes

- Passwords use Werkzeug's salted scrypt hashing; plaintext passwords are never stored. Password reset/change revokes every login session for that account.
- Opaque 48-byte random bearer tokens expire after eight hours. Only their SHA-256 hashes are stored. Streamlit holds the bearer token in its server-side session state; it is not placed in browser local storage or a custom auth cookie. Flask does not rely on cookie authentication, so no Flask `SECRET_KEY` is needed for this design.
- Each rerun revalidates the account with Flask. Logout deletes the backend session. Refreshing/reconnecting may require signing in again.
- Failed-login attempts are recorded in MySQL: five per account or thirty per source address in a rolling 15-minute window. Add a shared edge rate limiter for high-volume internet deployments and configure a trusted proxy carefully; the backend does not trust forwarded client IP headers by default.
- Never expose the Flask development server publicly. Use HTTPS at a reverse proxy, protect the Streamlit WebSocket route, keep Streamlit's XSRF protection enabled, and restrict backend/database network access. Do not expose backend credentials to students or coaches.
- Court and coach row locks serialize schedule writes; fee row locks serialize payment writes. MySQL foreign keys/unique/check constraints also protect integrity. Timestamps preserve microseconds so adjacent reservations remain valid.
- Payment recording is a ledger for externally received money, not a card gateway. Payment rows are immutable through the API. Refunds/reversals, online payment collection, email notifications, and multi-academy tenancy are outside this version.
- Monthly reports use the academy timezone for session boundaries and business dates for fees/payments. Month-end balances use current fee amounts and payments dated on/before month end; later fee edits affect regenerated reports. Retain exported reports for a fixed historical snapshot.
- Attendance counts present / past enrolled sessions excluding excused; unmarked past sessions remain in the denominator and are shown separately. No eligible sessions displays “—”. Scores are subjective coach assessments on a 0–100 scale where higher is better.
- Lists are scoped and designed for a single academy; very large deployments should add API pagination and server-side filtering before loading large datasets into Streamlit.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| `DATABASE_URL is required` | Run from the project root; create `.env` or set the MySQL environment variables |
| MySQL access denied | Check user, host grant, database, password URL encoding, and port |
| Missing table | Apply `flask --app backend:create_app db upgrade` |
| Cannot reach the academy API | Start Flask; check `API_URL`; native URLs differ from Compose service URLs |
| Login 401 | Select the correct role and ID; use the password supplied during provisioning; check account is active |
| Login 429 | Wait for the rolling 15-minute window; do not disable limits in production |
| Conflict 409 | Read the error; overlapping reservations, duplicate references, or protected history are expected validation failures |
| No students in session form | Assign active students to the selected active coach |
| Attendance rejected | Wait until session start and choose an enrolled student currently assigned to the coach |

## Documentation

- `PROJECT_EXPLANATION.md`: beginner-friendly architecture and modules.
- `API_DOCUMENTATION.md`: endpoint, role, payload, and error reference.
- `DATABASE_DOCUMENTATION.md`: tables, keys, constraints, and relationships.
- `TEST_RESULTS.md`: actual verification evidence and limits.
