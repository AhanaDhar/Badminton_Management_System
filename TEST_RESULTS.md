# Verification performed

Verified on **13 October 2026** using Python **3.12.14**, Streamlit **1.50.0**, Flask **3.1.2**, SQLAlchemy **2.0.43**, and a real **MySQL 8.4** container. These results describe executed checks, not promised coverage.

## Phase results

| Phase | Executed check | Result |
|---|---|---|
| Foundation | Authentication suite against isolated SQLite | 5 passed |
| Foundation | Initial Alembic schema upgrade on SQLite | Passed |
| Management APIs | Authentication + management/authorization suite on SQLite | 13 passed |
| Dashboards/reporting | Actual Streamlit scripts and Flask test client, analytics/seed/report tests | Passed after fixing test harness and timestamp issues |
| Final SQLite suite | `python -m pytest -q` | **22 passed, 2 skipped** in 20.22 s |
| Final MySQL suite | Dedicated MySQL URL + `python -m pytest -q` | **24 passed** in 28.80 s |
| Schema | Initial MySQL migration upgrade and `flask ... db check` | Passed; no new upgrade operations detected |
| Code checks | Ruff lint, Ruff format check, Python compileall | Passed; 33 Python files formatted |
| Native services | Gunicorn with 2 workers + MySQL; Streamlit on loopback | Started successfully |
| Live HTTP | API health; all three role logins; scoped analytics; monthly CSV; logout; Streamlit health and page response | Passed |
| Containers | Docker image build with optional CA secret | Passed |
| Containers | Image run as non-root user for Flask and Streamlit with MySQL connectivity | Both health endpoints returned HTTP 200 |
| Compose | `docker compose config --quiet` with validation environment values | Passed |

SQLite deliberately skips the two MySQL concurrency tests. No test substitutes SQLite locking behavior for MySQL verification. The complete Compose orchestration sequence was documented and its configuration validated; the individual Docker services were run, but a separate full Compose deployment lifecycle was not executed.

## What the tests cover

- Salted password hashing, login, incorrect role/password, rate limiting, expired/inactive sessions, logout, and password change revoking all sessions.
- Student/coach create/edit/delete, assignments, deactivation, unknown-field rejection, account/session removal, and protected dependent history.
- Scoped lists and direct-record authorization; Student cannot mutate academic or financial data; Coach cannot read fees/payments or another coach's assigned students.
- Court inventory CRUD, booking overlaps and adjacent boundaries, own-coach scheduling, coach overlap prevention, protected training reservations, and atomic session removal.
- Attendance enrollment/start-time requirements, upsert behavior, historical session/student deletion protection, excused/unmarked percentage semantics.
- Progress score bounds, author/student scope, feedback, tournaments/results and dependency protection.
- Decimal fee/payment balances, duplicate references, overpayment/fractional-cent rejection, paid-fee protection, financial visibility restrictions.
- Monthly payment/balance calculations, CSV structure, spreadsheet formula sanitization, report authorization/date validation.
- Realistic seed record counts and refusal to reseed an existing users table.
- Every sidebar page for Admin, Coach, and Student using Streamlit AppTest against actual Flask routes; login/logout; Admin creates and edits a coach through the UI.
- Concurrent MySQL booking requests produce one 201 and one 409; concurrent payments that would overpay produce one 201 and one 409.

## Issues found and fixed

MySQL's default datetime precision rounded reservation boundaries, causing an adjacent booking test to fail. Model and migration timestamps now use MySQL `DATETIME(6)`, preserving the precise interval boundaries. The MySQL suite now passes.

The pinned Streamlit AppTest version could not round-trip single-value segmented-control state. Login and action selectors now use native horizontal radio controls, and every role's page/navigation tests pass.

UI-thread writes were initially hidden by the MySQL snapshot held in the test fixture's main thread. Frontend tests now close the main-thread database session before reading results from another thread; normal production requests already have separate sessions.

## Not established by these checks

No manual browser screenshot/mobile-device review, internet deployment, TLS reverse-proxy configuration, load benchmark, penetration test, real financial gateway, or real external academy database was tested. Plotly charts execute in Streamlit tests; browser rendering/resizing across devices has not been manually inspected. The native Streamlit layout and configured theme are used without custom web markup.

The application is a functioning single-academy implementation. It does not provide payment reversals, automated email, multi-academy tenancy, API pagination, or a payment processor. These are explicitly outside the delivered feature set rather than simulated controls.

## Repeat the checks

Follow README.md to install dependencies and provision a **dedicated disposable MySQL test database**, then run:

```bash
python -m pytest -q
TEST_DATABASE_URL='mysql+pymysql://test_user:URL_ENCODED_PASSWORD@127.0.0.1:3306/badminton_test' python -m pytest -q
ruff check backend frontend tests
ruff format --check backend frontend tests migrations
```

Do not point the integration test fixture at production: it creates and drops domain tables. Local integration/preview passwords used during verification are not deployment credentials and are not written into `.env` or the deliverable configuration.
