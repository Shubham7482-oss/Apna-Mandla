# Root Cause Analysis: Alembic Migration Duplicate Table "settings" Error

## 1. The Root Cause

Historically, before Alembic migrations were introduced, the Apna Mandla application database schema was created directly on the target database at runtime using the SQLAlchemy core command:
```python
Base.metadata.create_all(bind=engine)
```
This created all the database tables (including the `settings` table) directly in the database. However, because this table creation was performed by SQLAlchemy's metadata manager and not through Alembic, the `alembic_version` tracking table was **never created or populated** with any migration history.

When the repository was transitioned to use Alembic migrations, the initial migration script `2263534f5211_initial_schema.py` was generated to represent the entire schema from scratch.

During deployment on Render:
- The persistent PostgreSQL database already contains all the tables (like `settings`, `users`, etc.) from previous deployments where `Base.metadata.create_all` was used.
- However, since these tables were created without Alembic, the `alembic_version` table is completely missing.
- When `alembic upgrade head` is executed during deployment, Alembic finds no registered migration history in the database, assumes the database is completely empty (at version `<base>`), and attempts to run the initial migration `2263534f5211_initial_schema.py` from scratch.
- The migration tries to execute `CREATE TABLE settings`, but the table already exists, resulting in the PostgreSQL error:
  `psycopg2.errors.DuplicateTable: relation "settings" already exists`

---

## 2. Why the Previous Fix Failed

The previous fix attempted to insert a conditional check directly into the migration file `2263534f5211_initial_schema.py` using `inspector.get_table_names()` to bypass the table creation if the table `settings` existed.

This failed and was rejected for several critical reasons:
1. **Rule Violations**: Checking table existence in `upgrade()` via an inspector or `IF EXISTS` blocks is an anti-pattern that circumvents standard Alembic version control, making migrations fragile, hard to maintain, and inconsistent.
2. **Untracked Versioning**: Skipping table creation in the initial migration still leaves the `alembic_version` table unpopulated or desynchronized, meaning Alembic still doesn't have a correct view of the current state of the database.
3. **User Disapproval**: This kind of hacky workaround is fundamentally brittle and explicitly prohibited by the engineering guidelines of this project.

---

## 3. The Proper Architectural Fix

To achieve a 100% clean, standard, and workaround-free database migration flow:

1. **Keep Migration Files Pristine**:
   - The initial migration file `2263534f5211_initial_schema.py` must be completely standard and clean, with **zero workarounds**, **zero conditional table skipping**, **zero `IF EXISTS` statements**, and **zero try/except blocks**.
   - This ensures that a fresh PostgreSQL database can be migrated perfectly from scratch.

2. **Reconcile Existing Database State (One-Time Architectural Stamping)**:
   - For existing databases that already have the schema but lack Alembic tracking, the standard, correct, and professional practice is to **stamp** the database with the initial revision ID using the Alembic stamp command:
     ```bash
     alembic stamp 2263534f5211
     ```
   - This creates the `alembic_version` table and inserts `2263534f5211` as the current version, without executing the initial migration steps (thus avoiding any duplicate table collisions).
   - Once stamped, running `alembic upgrade head` on Render will succeed perfectly (performing no actions since it is already up to date), and any future migrations will execute flawlessly.

---

# Addendum: Authentication Module Audit & Repair Report

## 1. Summary of Discovered Issues & Resolutions

As part of a complete end-to-end architectural audit and repair of the authentication system, several missing fields, schema mismatches, and third-party library incompatibilities were identified and resolved to make the module internally consistent and bulletproof.

### A. Missing Columns in `User` Model & Database
- **Issue**: The signup and login routes referenced several fields on the `User` model (`signup_ip`, `email`, `phone_verified`, `email_verified`, `is_archived`, `archived_at`) that were missing from both the `User` SQLAlchemy model and the original database schema.
- **Resolution**: Added `signup_ip`, `email`, `phone_verified`, and `email_verified` as columns on the `User` model (`Backend/app/models/user.py`). Changed the `User` model to inherit from `SoftArchiveMixin` to automatically incorporate `is_archived` and `archived_at` fields.

### B. SQLite and PostgreSQL-Compatible Alembic Migrations
- **Issue**: Standard table alteration (like column nullability or additions) can fail on certain dialects like SQLite because of the lack of `ALTER COLUMN` support.
- **Resolution**: Updated the Alembic migration script `c08fd113e94a_add_signup_ip_to_users_table.py` to use Alembic's `batch_alter_table` context manager. This ensures cross-compatibility and clean execution across both SQLite and PostgreSQL.

### C. Passwordless OTP Signup Support (Nullable `hashed_password`)
- **Issue**: The initial database schema defined `hashed_password` as `NOT NULL`. However, the secure signup flow creates the user record during the OTP step, before the user defines their password. This caused insertions to fail with `IntegrityError`.
- **Resolution**: Modified the `hashed_password` column to be nullable in both the SQLAlchemy model and the `c08fd113e94a` migration script to support OTP-only / passwordless intermediate states.

### D. Model & Attribute Consistency (`password_hash` vs. `hashed_password`)
- **Issue**: The `User` database column is named `hashed_password`, but several auth routes (like `/set-password`, `/reset-password`) and services set and retrieve `password_hash` directly on the `User` object, which would fail or go unsaved.
- **Resolution**: Implemented a clean property getter and setter for `password_hash` on the `User` model mapping it directly to the underlying `hashed_password` column.

### E. Passlib + Bcrypt 5.x Integration Failure
- **Issue**: Modern versions of the `bcrypt` library (v5.x or newer) removed the legacy `__about__` attribute, causing Passlib's version-checking block to throw `AttributeError` or `ValueError` even for short passwords under 72 bytes.
- **Resolution**: Explicitly pinned `bcrypt==4.3.0` in `Backend/requirements.txt` to guarantee clean, robust, and stable password hashing with `passlib` across all local, testing, and production environments.

### F. Pydantic v2 Exception Serialization TypeErrors
- **Issue**: Pydantic v2's custom validation exceptions (e.g. raised by validation checks in schemas) include `ValueError` or other python exception objects in the error list. When a validation error occurred, `validation_exception_handler` returned `exc.errors()` directly in `JSONResponse`, causing `json.dumps()` to throw a `TypeError: Object of type ValueError is not JSON serializable` on the server and return an HTTP 500 instead of HTTP 422.
- **Resolution**: Added a recursive serializer `_serialize_error_obj` inside `exception_handlers.py` that parses error list dictionaries and converts any custom exception or `ValueError` objects to their safe, string representations before returning them.

### G. Timezone-Naive vs. Timezone-Aware Datetime Subtraction
- **Issue**: SQLite represents database timestamps as timezone-naive when retrieved, causing `TypeError: can't subtract offset-naive and offset-aware datetimes` in `auth_login.py` when calculating OTP cooldown offsets.
- **Resolution**: Added robust timezone-handling checks to convert any naive datetimes retrieved from the database to UTC-aware datetimes before performing subtraction.

---

## 2. Dynamic End-To-End Verification Results

All of the following endpoints have been verified to work with 100% success using the spied end-to-end validation test script:
1. **POST `/api/v1/auth/signup`**: Returns HTTP 201 Created on registration and successfully mocks SMS delivery.
2. **POST `/api/v1/auth/register`**: Properly enforces collision-guard and returns HTTP 400.
3. **POST `/api/v1/auth/verify-otp` (signup)**: Successfully logs in and returns tokens (cookie path + Bearer tokens).
4. **POST `/api/v1/auth/login`**: Successfully issues a secure login OTP.
5. **POST `/api/v1/auth/verify-otp` (login)**: Successfully logs in and creates device sessions.
6. **POST `/api/v1/auth/set-password`**: Successfully sets/changes password.
7. **POST `/api/v1/auth/forgot-password`**: Successfully issues a password reset OTP.
8. **POST `/api/v1/auth/reset-password`**: Successfully resets password with OTP validation.
9. **POST `/api/v1/auth/refresh`**: Successfully rotates both refresh and access tokens.
10. **GET `/api/v1/auth/sessions`**: Correctly lists all active, non-revoked device sessions.
11. **DELETE `/api/v1/auth/sessions/{session_id}`**: Revokes specific sessions securely (IDOR-guarded).
12. **DELETE `/api/v1/auth/sessions`**: Successfully revokes other sessions while keeping current session active.
13. **POST `/api/v1/auth/logout`**: Successfully revokes current session.
14. **POST `/api/v1/auth/logout-all`**: Successfully revokes all sessions across all devices for the user.
