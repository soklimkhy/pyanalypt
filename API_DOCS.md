# PyAnalypt API Documentation

## Base URLs

- **Development**: `http://127.0.0.1:8000/api/v1/`
- **Production**: `https://api.pyanalypt.com/api/v1/`

## Authentication

All protected endpoints require a JWT `access` token in the Authorization header:
```
Authorization: Bearer <access_token>
```

**Token Lifetimes**:
- Access Token: **60 minutes**
- Refresh Token: **1 day**
- Rotation: Enabled — new refresh token issued on every refresh call.

---

## 🔐 Authentication Endpoints

### 1. Register New User (Step 1)
Create a new inactive account with just email and password. A 6-digit verification code is sent to the email.

- **Endpoint**: `POST /auth/registration/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```
> Only `email` and `password` are required. No confirmation password field is needed on the backend.

- **Response (201 Created)**:
```json
{
  "detail": "Initial registration successful. Please check your email for the 6-digit verification code."
}
```

---

### 2. Resend Registration OTP
Request a new 6-digit verification code if the previous one expired or was not received.

- **Endpoint**: `POST /auth/registration/resend-otp/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "email": "user@example.com"
}
```
- **Response (200 OK)**:
```json
{
  "detail": "A new verification code has been sent to your email."
}
```

---

### 3. Verify Registration OTP (Step 2)
Activate the account and verify the email address. On success, JWT tokens are issued. The user is now authenticated but must complete their profile.

- **Endpoint**: `POST /auth/registration/verify-otp/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```
- **Response (200 OK)**:
```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>",
  "requires_profile_completion": true,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "user_1234567890",
    "full_name": "",
    "birthday": null,
    "profile_picture": null,
    "email_verified": true,
    "is_staff": false,
    "is_active": true,
    "date_joined": "2026-03-21T00:00:00Z",
    "last_login": "2026-03-21T06:00:00Z"
  }
}
```

---

### 4. Complete Profile (Step 3)
Finalize the registration by setting a unique username, full name, and birthday. Can only be called once — calling it again after the profile is already set returns a 400 error.

- **Endpoint**: `POST /auth/registration/complete-profile/`
- **Auth Required**: Yes (JWT access token)
- **Request Body**:
```json
{
  "username": "johndoe",
  "full_name": "John Doe",
  "birthday": "1995-05-20"
}
```
- **Response (200 OK)**:
```json
{
  "detail": "Profile completed successfully.",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "johndoe",
    "full_name": "John Doe",
    "birthday": "1995-05-20",
    "email_verified": true,
    "is_active": true
  }
}
```
- **Response (400)** if profile is already completed:
```json
{
  "detail": "Profile has already been completed."
}
```

> **Frontend flow:**
> 1. User submits email/password → `POST /auth/registration/`
> 2. On `201 Created` → redirect to `/verify-otp?email=user@example.com`
> 3. User enters 6-digit code → `POST /auth/registration/verify-otp/`
> 4. On `200 OK` → store tokens and redirect to `/complete-profile`
> 5. User enters username, name, and birthday → `POST /auth/registration/complete-profile/`
> 6. On `200 OK` → redirect to `/dashboard`


---

### 5. Login
Log in with **email and password**. The response differs depending on whether the user has 2FA enabled.

- **Endpoint**: `POST /auth/login/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

#### Case A — 2FA disabled (normal login)
- **Response (200 OK)**:
```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>",
  "requires_profile_completion": true,
  "user": { ... }
}
```
> **IMPORTANT**: Check for `requires_profile_completion`. If `true`, the user has verified their email but has **not** completed Step 3 (username/full_name/birthday). Redirect them to `/complete-profile`.

#### Case B — 2FA enabled
- **Response (202 Accepted)**:
```json
{
  "requires_2fa": true,
  "totp_token": "<token>"
}
```

#### Case C — Email Not Verified
- **Response (403 Forbidden)**:
```json
{
  "detail": "Email address not verified.",
  "requires_verification": true,
  "email": "user@example.com"
}
```
> **IMPORTANT**: If the user tries to log in with an unverified email, they are blocked. Redirect them back to the `/verify-otp` page using the `email` provided in the response.
> **No JWT tokens are issued yet.** The `totp_token` expires in **5 minutes**.
> Frontend must redirect to the 2FA code screen and call [`POST /auth/2fa/verify-login/`](#10-complete-login-with-2fa-code) to finish.

> **Frontend flow for 2FA login:**
> 1. `POST /auth/login/` → check if `requires_2fa === true`
> 2. If yes → store `totp_token` in component state (not localStorage)
> 3. Show a 6-digit code input screen
> 4. User opens Google Authenticator, enters the code
> 5. `POST /auth/2fa/verify-login/` with `{ totp_token, code }` → receive JWT tokens
> 6. If `totp_token` expires → send user back to login

---

### 6. Logout
Invalidate the current session by blacklisting the refresh token.

- **Endpoint**: `POST /auth/logout/`
- **Auth Required**: Yes
- **Request Body**:
```json
{
  "refresh": "<refresh_token>"
}
```
- **Response (200 OK)**:
```json
{
  "detail": "Successfully logged out."
}
```

---

### 7. Get Current User
Retrieve profile information for the authenticated user.

- **Endpoint**: `GET /auth/user/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "birthday": "1995-05-20",
  "profile_picture": null,
  "email_verified": true,
  "is_staff": false,
  "is_active": true,
  "date_joined": "2026-03-21T00:00:00Z",
  "last_login": "2026-03-21T06:00:00Z"
}
```

---

### 8. Update Profile
Update one or more profile fields. Send only the fields you want to change — unset fields are left as-is. `email` is the only permanently read-only field.

- **Endpoint**: `PATCH /auth/user/`
- **Auth Required**: Yes

| Field | Writable | Validation |
|---|---|---|
| `username` | ✅ Yes | 3–150 chars; letters, numbers, dots, underscores, hyphens only; must be unique |
| `full_name` | ✅ Yes | 2–255 chars; letters, hyphens, apostrophes, and spaces only |
| `birthday` | ✅ Yes | YYYY-MM-DD; must be in the past and no more than 120 years ago |
| `profile_picture` | ✅ Yes | Must be a valid HTTPS URL; send `null` to clear |
| `email` | ❌ Read-only | Cannot be changed |

- **Request Body** *(any subset of writable fields)*:
```json
{
  "username": "johnny",
  "full_name": "Jonathan Doe",
  "birthday": "1995-05-20",
  "profile_picture": "https://example.com/avatar.jpg"
}
```
- **Response (200 OK)**: Full user object (same shape as `GET /auth/user/`).
- **Response (400)** examples:
```json
{ "username": ["This username is already taken."] }
{ "birthday": ["Birthday must be in the past."] }
{ "profile_picture": ["Profile picture URL must use HTTPS protocol for security."] }
```

---

### 9. Change Password
Change password while authenticated. The current session stays active; all **other** active sessions are revoked automatically so other devices are forced to log in again.

- **Endpoint**: `POST /auth/password/change/`
- **Auth Required**: Yes
- **Rate Limit**: 5 requests/hour per user
- **Request Body**:
```json
{
  "old_password": "CurrentPass123!",
  "new_password1": "NewSecurePass456!",
  "new_password2": "NewSecurePass456!"
}
```
- **Response (200 OK)**:
```json
{
  "detail": "New password has been saved."
}
```
- **Response (400)** if `old_password` is wrong:
```json
{
  "old_password": ["Your old password was entered incorrectly. Please enter it again."]
}
```

> All sessions except the one making this request are blacklisted immediately. The current device stays logged in.

---

### 10. Password Reset (Forgot Password)
Send a password reset link to the user's email.

**Step 1 — Request reset email**
- **Endpoint**: `POST /auth/password/reset/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "email": "user@example.com"
}
```
- **Response (200 OK)**:
```json
{
  "detail": "Password reset e-mail has been sent."
}
```

**Step 2 — Confirm new password**
- **Endpoint**: `POST /auth/password/reset/confirm/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "uid": "<uid_from_reset_link>",
  "token": "<token_from_reset_link>",
  "new_password1": "NewSecurePass456!",
  "new_password2": "NewSecurePass456!"
}
```
- **Response (200 OK)**:
```json
{
  "detail": "Password has been reset with the new password."
}
```

> **Frontend flow:**
> 1. User submits their email on the "Forgot Password" page → `POST /auth/password/reset/`
> 2. User receives email with a link like `http://localhost:3000/reset-password/<uid>/<token>/`
> 3. Frontend extracts `uid` and `token` from the URL
> 4. User types a new password → `POST /auth/password/reset/confirm/` with `uid`, `token`, and both password fields
> 5. On `200 OK` → redirect to `/login`

---

## 🔑 JWT Token Management

### 11. Refresh Access Token
Exchange a refresh token for a new access token. A new refresh token is also returned (rotation enabled). The active session record is updated automatically.

- **Endpoint**: `POST /auth/token/refresh/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "refresh": "<refresh_token>"
}
```
- **Response (200 OK)**:
```json
{
  "access": "<new_access_token>",
  "refresh": "<new_refresh_token>"
}
```
> Always replace both stored tokens when this endpoint responds. The old refresh token is immediately invalidated.

### 12. Verify Token
Check if an access or refresh token is still valid.

- **Endpoint**: `POST /auth/token/verify/`
- **Auth Required**: No
- **Request Body**: `{ "token": "<token>" }`
- **Response (200 OK)**: `{}` *(empty body = valid)*
- **Response (401)**: Token is expired or invalid.

---

## 🔒 Two-Factor Authentication (TOTP)

All 2FA endpoints require the user to be **logged in** (JWT Bearer token), except `verify-login` which is used before tokens are issued.

### 13. Setup 2FA — Get QR Code
Generates a new TOTP secret and returns the `otpauth://` URI for rendering a QR code. This does **not** enable 2FA yet — the user must scan and confirm first.

- **Endpoint**: `GET /auth/2fa/setup/`
- **Auth Required**: Yes
- **Rate Limit**: 20 requests/hour per user
- **Response (200 OK)**:
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "otpauth_uri": "otpauth://totp/PyAnalypt:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=PyAnalypt"
}
```

> **Frontend flow:**
> 1. Call `GET /auth/2fa/setup/`
> 2. Render `otpauth_uri` as a QR code using a library like [`qrcode.react`](https://www.npmjs.com/package/qrcode.react)
> 3. Also show the raw `secret` as a fallback for manual entry in Google Authenticator
> 4. Prompt user to scan and enter their first code to confirm → `POST /auth/2fa/enable/`

---

### 14. Enable 2FA
Activates 2FA by verifying the first TOTP code from the authenticator app. Must be called after `GET /auth/2fa/setup/`.

- **Endpoint**: `POST /auth/2fa/enable/`
- **Auth Required**: Yes
- **Rate Limit**: 20 requests/hour per user
- **Request Body**:
```json
{
  "code": "123456"
}
```
> `code` must be exactly **6 digits** (e.g. `"123456"`). Non-digit characters are rejected.
- **Response (200 OK)**:
```json
{
  "detail": "2FA enabled successfully."
}
```
- **Response (400)** if code is wrong:
```json
{
  "code": ["Invalid or expired code."]
}
```

---

### 15. Disable 2FA
Turns off 2FA. Requires both the current password and a valid TOTP code to confirm intent.

- **Endpoint**: `POST /auth/2fa/disable/`
- **Auth Required**: Yes
- **Rate Limit**: 20 requests/hour per user
- **Request Body**:
```json
{
  "code": "123456",
  "password": "CurrentPassword123!"
}
```
> `code` must be exactly **6 digits**. Non-digit characters are rejected.
- **Response (200 OK)**:
```json
{
  "detail": "2FA disabled successfully."
}
```

---

### 16. Complete Login with 2FA Code
Finishes a login that was paused by the 2FA gate. Receives the same JWT response as a normal login.

- **Endpoint**: `POST /auth/2fa/verify-login/`
- **Auth Required**: No *(user is not authenticated yet at this point)*
- **Rate Limit**: 10 requests/hour per IP
- **Request Body**:
```json
{
  "totp_token": "<token_from_login_response>",
  "code": "123456"
}
```
> `code` must be exactly **6 digits**. `totp_token` comes from the `202 Accepted` response of `POST /auth/login/` or `POST /auth/google/`.

- **Response (200 OK)**:
```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "username": "johndoe",
    "full_name": "John Doe",
    "birthday": "1995-05-20",
    "profile_picture": null,
    "email_verified": true,
    "is_staff": false,
    "is_active": true,
    "date_joined": "2026-03-21T00:00:00Z",
    "last_login": "2026-03-21T06:00:00Z"
  }
}
```
- **Response (400)** if `totp_token` expired (> 5 minutes):
```json
{
  "detail": "Token expired, please log in again."
}
```
- **Response (400)** if account has been deactivated:
```json
{
  "detail": "Account is disabled."
}
```

---

## 📱 Session Management

Each login creates a session record that tracks the device, browser, and IP address. Sessions are tied to refresh tokens — revoking a session blacklists its token immediately.

### Session Object

| Field | Type | Description |
|---|---|---|
| `id` | int | Session identifier |
| `device` | string | Device family (e.g. `"iPhone"`, `"Desktop"`) |
| `browser` | string | Browser and OS (e.g. `"Chrome on Windows"`) |
| `ip_address` | string | IP address at login |
| `created_at` | datetime | When the session was created (login time) |
| `last_active` | datetime | Last time the refresh token was used |
| `is_current` | boolean | `true` if this session belongs to the token making the request |

---

### 17. List Active Sessions
Returns all active sessions for the current user.

- **Endpoint**: `GET /auth/sessions/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
[
  {
    "id": 3,
    "device": "Desktop",
    "browser": "Chrome on Windows",
    "ip_address": "192.168.1.10",
    "created_at": "2026-04-14T08:00:00Z",
    "last_active": "2026-04-14T09:30:00Z",
    "is_current": true
  },
  {
    "id": 4,
    "device": "iPhone",
    "browser": "Mobile Safari on iOS",
    "ip_address": "10.0.0.5",
    "created_at": "2026-04-13T20:00:00Z",
    "last_active": "2026-04-13T20:45:00Z",
    "is_current": false
  }
]
```

> **Frontend tip:** Use `is_current: true` to highlight and protect the active session in the UI. When building a "sign out all other devices" flow, skip the session where `is_current` is `true` and call `DELETE /auth/sessions/{id}/` on the rest, or use `POST /auth/sessions/revoke-all/` (which revokes everything including the current session).

---

### 18. Revoke a Specific Session
Blacklists the refresh token for that session, forcing that device to log in again.

- **Endpoint**: `DELETE /auth/sessions/{id}/`
- **Auth Required**: Yes
- **Response (204 No Content)**: *(empty — success)*
- **Response (404)**: Session not found or doesn't belong to the current user.

---

### 19. Revoke All Sessions (Logout Everywhere)
Blacklists **all** active sessions for the current user, including the current one. The user will need to log in again on all devices.

- **Endpoint**: `POST /auth/sessions/revoke-all/`
- **Auth Required**: Yes
- **Request Body**: *(empty)*
- **Response (200 OK)**:
```json
{
  "detail": "Revoked 3 session(s)."
}
```

> **Frontend tip:** After calling this endpoint, immediately clear stored tokens and redirect to `/login`.

---

## 🌐 Google OAuth

### 20. Google Login
Exchange a Google OAuth `access_token` for PyAnalypt JWT tokens. New users are registered automatically.

- **Endpoint**: `POST /auth/google/`
- **Auth Required**: No
- **Request Body**:
```json
{
  "access_token": "<google_access_token>"
}
```

#### Case A — 2FA disabled (normal)
- **Response (200 OK)**: Same shape as normal login (access + refresh + user).

#### Case B — 2FA enabled on the account
- **Response (202 Accepted)**:
```json
{
  "requires_2fa": true,
  "totp_token": "<short_lived_signed_token>"
}
```
> JWT tokens are **not** issued yet. Pass `totp_token` to `POST /auth/2fa/verify-login/` with the TOTP code to complete login. The token expires in **5 minutes**.

> **Frontend flow:**
> 1. Trigger Google Sign-In using the Google Identity SDK
> 2. On success, receive a Google `access_token`
> 3. `POST /api/v1/auth/google/` with `{ "access_token": "<google_token>" }`
> 4. If `requires_2fa === true` → treat identically to the 2FA branch of `POST /auth/login/` (show code screen, call `POST /auth/2fa/verify-login/`)
> 5. Otherwise, store the returned JWT tokens normally

---

## 🛡️ Admin Access

PyAnalypt provides a full administrative interface for managing users and system data.

- **Admin URL**: `http://127.0.0.1:8000/admin/`
- **Default Credentials**: 
  - **Email**: `admin@pyanalypt.com`
  - **Password**: `admin123!@#`

---

## 📂 Dataset Management

All endpoints below are under `/api/v1/datasets/`.

### Dataset Object

| Field | Type | Description |
|---|---|---|
| `id` | int | Unique identifier |
| `user` | int | Owner user ID |
| `file` | string | URL to the stored file |
| `file_name` | string | Display name of the file |
| `file_format` | string | File extension (`csv`, `xlsx`, `json`, `parquet`) |
| `file_size` | int | File size in bytes |
| `uploaded_date` | datetime | When the file was first uploaded |
| `updated_date` | datetime | Last modification timestamp |

### 1. Upload File
Standard multipart/form-data upload.

- **Endpoint**: `POST /datasets/upload/`
- **Auth Required**: Yes
- **Request (Form Data)**:
  - `file`: The `.csv`, `.xlsx`, `.json`, or `.parquet` file.
- **Response (201 Created)**: The newly created `Dataset` object.

### 2. List All Datasets
Retrieves all datasets owned by the authenticated user.

- **Endpoint**: `GET /datasets/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
[
  {
    "id": 15,
    "user": 1,
    "file": "http://.../datasets/survey.csv",
    "file_name": "survey.csv",
    "file_format": "csv",
    "file_size": 1048576,
    "uploaded_date": "2026-03-17T10:00:00Z",
    "updated_date": "2026-03-17T10:30:00Z"
  }
]
```

### 3. Delete Dataset
Removes the dataset record and its associated file from storage. Also logs the DELETE action.

- **Endpoint**: `DELETE /datasets/{id}/`
- **Auth Required**: Yes
- **Response (204 No Content)**

### 4. Rename Dataset
Rename the display file name of a dataset.

- **Endpoint**: `PATCH /datasets/{id}/rename/`
- **Auth Required**: Yes
- **Request Body**:
```json
{
  "file_name": "renamed_data.csv"
}
```
- **Response (200 OK)**: Updated `Dataset` object.
- **Response (400)** if `file_name` is missing or blank.

### 5. Export Dataset
Download the dataset converted to a requested format. Defaults to the dataset's original format if `?format` is omitted.

- **Endpoint**: `GET /datasets/{id}/export/`
- **Auth Required**: Yes
- **Query Params**: `?format=csv` *(options: `csv`, `json`, `xlsx`, `parquet`)*
- **Response**: Binary file download with appropriate `Content-Disposition` header.
- **Response (400)** if the format is unsupported.

### 6. Duplicate Dataset
Clone an existing dataset into a new record. Supports on-the-fly format conversion and maintains data lineage via the `parent` field.

- **Endpoint**: `POST /datasets/{id}/duplicate/`
- **Auth Required**: Yes
- **Request Body**:
```json
{
  "new_file_name": "Sales Copy",
  "format": "csv"
}
```
> Both fields are optional. `new_file_name` defaults to `<original>_copy`. `format` defaults to the source dataset's format. Supported formats: `csv`, `json`, `xlsx`, `parquet`.

- **Response (201 Created)**: `Dataset` object of the new clone.

### 7. Activity Logs
Retrieve a stream of activities performed on datasets.

- **Endpoint**: `GET /datasets/activity_logs/`
- **Auth Required**: Yes
- **Query Params**: `?dataset={id}` *(optional — filter logs by a specific dataset)*
- **Response (200 OK)**:
```json
[
  {
    "id": 42,
    "user": 1,
    "dataset": 15,
    "dataset_name_snap": "survey.csv",
    "action": "UPLOAD",
    "details": {},
    "timestamp": "2026-03-17T10:00:00Z"
  }
]
```

**All logged action types:**

| Action | Triggered by | `details` payload |
|---|---|---|
| `UPLOAD` | File upload | `{}` |
| `RENAME` | Dataset rename | `{}` |
| `DELETE` | Dataset delete | `{}` |
| `DUPLICATE` | Dataset duplicate | `{}` |
| `EXPORT` | Dataset export | `{}` |
| `UPDATE_CELL` | Update cell | `{ row_index, column, value }` |
| `CAST` | Cast columns | `{ columns: { col: type } }` |
| `RENAME_COLUMN` | Rename column | `{ old_name, new_name }` |
| `DROP_DUPLICATES` | Drop duplicates | `{ mode, rows_dropped }` |
| `REPLACE_VALUES` | Replace values | `{ cells_replaced, columns }` |
| `DROP_NULLS` | Drop nulls | `{ axis, rows_dropped }` or `{ axis, columns_dropped }` |
| `FILL_NULLS` | Fill nulls | `{ strategy, cells_filled }` |
| `FILL_DERIVED` | Fill derived | `{ target, formula, cells_filled }` |
| `FIX_FORMULA` | Fix formula | `{ target, formula, cells_fixed }` |
| `TRIM_OUTLIERS` | Trim outliers | `{ method, threshold, rows_dropped }` |
| `IMPUTE_OUTLIERS` | Impute outliers | `{ method, strategy, cells_imputed }` |
| `CAP_OUTLIERS` | Cap outliers | `{ lower_pct, upper_pct, cells_capped }` |
| `TRANSFORM_COLUMN` | Transform column | `{ function, columns }` |
| `DROP_COLUMNS` | Drop columns | `{ columns_dropped }` |
| `ADD_COLUMN` | Add derived column | `{ new_name, formula, operand_a, operand_b }` |
| `FILTER_ROWS` | Filter rows | `{ column, operator, value, rows_removed }` |
| `CLEAN_STRING` | Clean string columns | `{ operation, columns, cells_changed }` |
| `SCALE_COLUMNS` | Scale numeric columns | `{ method, columns }` |
| `EXTRACT_DATETIME` | Extract datetime features | `{ source_column, added_columns }` |
| `ENCODE_COLUMNS` | Encode categorical columns | `{ strategy, columns }` |
| `NORMALIZE_COLUMN_NAMES` | Normalize column headers | `{ renamed }` |
| `REVERT` | Revert to snapshot | `{ snapshot_id, was_undo }` |

---

## 🧪 Datalab

The Datalab is the **data wrangling layer** — inspect, clean, transform, and audit datasets before analysis. It covers the full preparation pipeline: preview, inspect, type casting, null handling, deduplication, formula validation, and outlier treatment.

All endpoints below are under `/api/v1/datalab/`.

| # | Method | Endpoint | Description |
|---|--------|----------|-------------|
| 1 | `GET` | `/datalab/preview/{dataset_id}/` | Render dataset as a data table |
| 2 | `GET` | `/datalab/inspect/{dataset_id}/` | Return per-column dtype, null counts, null %, and memory usage |
| 3 | `GET` | `/datalab/describe/{dataset_id}/` | Return descriptive statistics for all columns (`df.describe()`) |
| 4 | `POST` | `/datalab/fill-derived/{dataset_id}/` | Fill nulls in a column by deriving values from two other columns using arithmetic |
| 5 | `POST` | `/datalab/validate-formula/{dataset_id}/` | Check whether a column's values match a formula across two operand columns |
| 6 | `POST` | `/datalab/fix-formula/{dataset_id}/` | Overwrite inconsistent values in a column by recomputing from trusted columns |
| 7 | `POST` | `/datalab/cast/{dataset_id}/` | Cast one or more columns to a new dtype and persist the change |
| 8 | `POST` | `/datalab/drop-duplicates/{dataset_id}/` | Remove duplicate rows and persist the cleaned dataset |
| 9 | `POST` | `/datalab/rename-column/{dataset_id}/` | Rename a column header and persist the change |
| 10 | `PATCH` | `/datalab/update-cell/{dataset_id}/` | Edit a single cell value with dtype validation |
| 11 | `POST` | `/datalab/replace-values/{dataset_id}/` | Replace sentinel/garbage values with NaN or another value |
| 12 | `POST` | `/datalab/drop-nulls/{dataset_id}/` | Drop rows or columns containing null values |
| 13 | `POST` | `/datalab/fill-nulls/{dataset_id}/` | Fill null values using a chosen imputation strategy |
| 14 | `GET` | `/datalab/detect-outliers/{dataset_id}/` | Detect outliers per column using IQR or Z-Score — read-only audit |
| 15 | `POST` | `/datalab/trim-outliers/{dataset_id}/` | Delete rows where any target column has an outlier value |
| 16 | `POST` | `/datalab/impute-outliers/{dataset_id}/` | Replace outlier values with column mean, median, or mode |
| 17 | `POST` | `/datalab/cap-outliers/{dataset_id}/` | Winsorize — cap values at lower/upper percentile bounds |
| 18 | `POST` | `/datalab/transform-column/{dataset_id}/` | Apply log, sqrt, or cbrt transformation to numeric columns |
| 19 | `POST` | `/datalab/drop-columns/{dataset_id}/` | Drop one or more columns entirely from the dataset |
| 20 | `POST` | `/datalab/add-column/{dataset_id}/` | Create a new column computed from two existing columns using arithmetic |
| 21 | `POST` | `/datalab/filter-rows/{dataset_id}/` | Keep only rows that match a condition — discard the rest |
| 22 | `POST` | `/datalab/clean-string/{dataset_id}/` | Apply string operations (strip whitespace, change case) to text columns |
| 23 | `POST` | `/datalab/scale-columns/{dataset_id}/` | Normalize numeric columns using min-max `[0,1]` or z-score scaling |
| 24 | `POST` | `/datalab/extract-datetime/{dataset_id}/` | Extract year/month/day/weekday/hour/minute from a datetime column into new columns |
| 25 | `POST` | `/datalab/encode-columns/{dataset_id}/` | Encode categorical columns as integers (label) or binary indicators (one-hot) |
| 26 | `POST` | `/datalab/normalize-column-names/{dataset_id}/` | Rename all column headers to `lowercase_snake_case` |
| 27 | `POST` | `/datalab/revert/{dataset_id}/` | Revert to a previous snapshot or undo the last mutation |

---

### 1. Preview Dataset as Table

Returns a row-limited slice of the dataset rendered as rows and columns for display in a data table component.

- **Endpoint**: `GET /datalab/preview/{dataset_id}/`
- **Auth Required**: Yes
- **Query Params**:

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | `100` | Number of rows to return. `0` = all rows, capped at 10,000. Max positive value: `10,000`. |

Typical UI values: `100`, `200`, `500`, `0` (All).

- **Response (200 OK)**:
```json
{
  "dataset_id": 15,
  "file_name": "survey.csv",
  "file_format": "csv",
  "dataset_size": "1.0 MB",
  "total_rows": 1000,
  "total_columns": 3,
  "limit": 100,
  "truncated": false,
  "columns": ["Name", "Age", "Salary"],
  "rows": [
    { "Name": "Alice", "Age": 30, "Salary": 50000 },
    { "Name": "Bob", "Age": null, "Salary": 62000 }
  ]
}
```

- **Response (400)** — limit exceeds maximum:
```json
{ "detail": "'limit' cannot exceed 10000." }
```

- **Response (400)** — invalid limit:
```json
{ "detail": "'limit' must be a non-negative integer (0 = all rows, max 10000)." }
```

> `null` is used for missing values (`NaN`). The `columns` array preserves the original column order.
> `dataset_size` is a human-readable string (`B`, `KB`, `MB`, `GB`, `TB`).
> `total_rows` always reflects the full dataset regardless of `limit`.
> `truncated: true` means the dataset has more rows than what was returned — show a "Showing X of Y rows" indicator in the UI.
> `limit=0` returns up to 10,000 rows (capped). If `total_rows > 10,000` and `truncated: true`, the user is only seeing the first 10,000.

---

### 2. Inspect DataFrame Metadata

Returns structured per-column metadata: dtype, null counts, null percentage, and total memory usage.

- **Endpoint**: `GET /datalab/inspect/{dataset_id}/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
{
  "info": {
    "columns": [
      {
        "column": "user_id",
        "dtype": "int64",
        "non_null_count": 1000,
        "null_count": 0,
        "null_pct": 0.0,
        "unique_count": 1000,
        "is_unique": true
      },
      {
        "column": "Age",
        "dtype": "float64",
        "non_null_count": 988,
        "null_count": 12,
        "null_pct": 1.2,
        "unique_count": 72,
        "is_unique": false
      },
      {
        "column": "Salary",
        "dtype": "int64",
        "non_null_count": 1000,
        "null_count": 0,
        "null_pct": 0.0,
        "unique_count": 540,
        "is_unique": false
      }
    ],
    "memory_usage_bytes": 24128
  }
}
```

> `info.columns` is the structured per-column breakdown — use this to render the inspect table.
> `null_pct` is rounded to 1 decimal place (e.g. `1.2` means 1.2% of rows are null for that column).
> `unique_count` is the number of distinct non-null values in the column.
> `is_unique` is `true` when every **non-null** value in the column is distinct. Columns with nulls can still be `is_unique: true` — use it to identify ID/key columns (`user_id`, `transaction_id`, `product_id`, etc.).
> `memory_usage_bytes` is the total deep memory usage of the dataframe in bytes.

---

### 3. Describe Dataset (Summary Statistics)

Returns descriptive statistics for every column using pandas `df.describe(include='all')`. Numeric columns get distribution stats; categorical/string columns get frequency stats. `NaN` stats are omitted from the response.

- **Endpoint**: `GET /datalab/describe/{dataset_id}/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
{
  "columns": {
    "Age": {
      "count": 988.0,
      "mean": 35.2,
      "std": 12.1,
      "min": 18.0,
      "25%": 25.0,
      "50%": 34.0,
      "75%": 45.0,
      "max": 72.0
    },
    "Salary": {
      "count": 1000.0,
      "mean": 58400.0,
      "std": 14200.0,
      "min": 22000.0,
      "25%": 48000.0,
      "50%": 56000.0,
      "75%": 68000.0,
      "max": 120000.0
    },
    "Country": {
      "count": 1000.0,
      "unique": 42.0,
      "top": "United States",
      "freq": 312.0
    }
  }
}
```

> **Numeric columns** — `count`, `mean`, `std`, `min`, `25%`, `50%`, `75%`, `max`.
> **Categorical / string columns** — `count`, `unique`, `top` (most frequent value), `freq` (how many times it appears).
> Stats that don't apply to a column type (e.g. `mean` on a string column) are omitted — not returned as `null`.
> `count` reflects non-null rows only — compare against `total_rows` from `inspect` to derive the null count.

---

### 4. Fill Derived Values

Fill null values in a target column by computing them from two other columns using arithmetic. Only fills rows where the target is null **and** both operand columns have non-null values (and a non-zero denominator for `divide`).

- **Endpoint**: `POST /datalab/fill-derived/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `target` | string | Yes | Column whose nulls should be filled |
| `formula` | string | Yes | Arithmetic operation: `"divide"`, `"multiply"`, `"add"`, `"subtract"` |
| `operand_a` | string | Yes | Left-hand column in the formula |
| `operand_b` | string | Yes | Right-hand column in the formula |

The fill value is computed as: `target = operand_a <formula> operand_b`

**Fill missing `Unit_Price` from `Total_Price ÷ Quantity`:**
```json
{
  "target": "Unit_Price",
  "formula": "divide",
  "operand_a": "Total_Price",
  "operand_b": "Quantity"
}
```

**Fill missing `Quantity` from `Total_Price ÷ Unit_Price` (rounded to integer):**
```json
{
  "target": "Quantity",
  "formula": "divide",
  "operand_a": "Total_Price",
  "operand_b": "Unit_Price"
}
```

**Fill missing `Total_Price` from `Quantity × Unit_Price`:**
```json
{
  "target": "Total_Price",
  "formula": "multiply",
  "operand_a": "Quantity",
  "operand_b": "Unit_Price"
}
```

#### Responses

- **Response (200)** — nulls filled:
```json
{
  "target": "Unit_Price",
  "formula": "divide",
  "operand_a": "Total_Price",
  "operand_b": "Quantity",
  "cells_filled": 23
}
```

- **Response (200)** — nothing to fill (no file write occurs):
```json
{
  "target": "Unit_Price",
  "formula": "divide",
  "operand_a": "Total_Price",
  "operand_b": "Quantity",
  "cells_filled": 0,
  "detail": "No null values in 'Unit_Price' with complete operand data."
}
```

- **Response (400)** — missing fields:
```json
{ "detail": "'target', 'formula', 'operand_a', and 'operand_b' are all required." }
```
- **Response (400)** — invalid formula:
```json
{ "detail": "Invalid 'formula'. Choose one of: ['divide', 'multiply', 'add', 'subtract']" }
```
- **Response (400)** — non-numeric columns (target or operands):
```json
{ "detail": "All three columns must be numeric: ['Quantity']" }
```

> All three columns — `target`, `operand_a`, and `operand_b` — must be numeric.
> If `target` is an integer-typed column, derived values are automatically rounded and cast to `Int64`.
> Rows where `operand_b = 0` are skipped when `formula` is `"divide"` — they remain null.
> Run `fill_derived` **before** `fill_nulls` — this fills the recoverable nulls first; use `fill_nulls` for the rest.

---

### 5. Validate Formula

Check whether a column's values are mathematically consistent with a formula across two other columns. Read-only — does not modify the dataset. Use this after `fill_derived` to verify correctness, or as a data quality check on raw uploads.

- **Endpoint**: `POST /datalab/validate-formula/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `result_column` | string | Yes | Column that should equal `operand_a <formula> operand_b` |
| `formula` | string | Yes | `"divide"`, `"multiply"`, `"add"`, `"subtract"` |
| `operand_a` | string | Yes | Left-hand operand column |
| `operand_b` | string | Yes | Right-hand operand column |
| `tolerance` | number | No | Acceptable absolute difference. Defaults to `0.01` (1 cent) |

**Check that `Total_Price ≈ Quantity × Unit_Price` within 1 cent:**
```json
{
  "result_column": "Total_Price",
  "formula": "multiply",
  "operand_a": "Quantity",
  "operand_b": "Unit_Price",
  "tolerance": 0.01
}
```

#### Responses

- **Response (200)** — validation complete:
```json
{
  "result_column": "Total_Price",
  "formula": "multiply",
  "operand_a": "Quantity",
  "operand_b": "Unit_Price",
  "tolerance": 0.01,
  "total_rows": 1000,
  "checked_rows": 950,
  "error_rows": 12,
  "error_pct": 1.3,
  "sample_errors": [
    {
      "row_index": 42,
      "Quantity": 3,
      "Unit_Price": 15.99,
      "Total_Price": 50.00,
      "calculated": 47.97,
      "diff": 2.03
    }
  ]
}
```

- **Response (200)** — no checkable rows (all null or zero denominator):
```json
{
  "result_column": "Total_Price",
  "formula": "multiply",
  "operand_a": "Quantity",
  "operand_b": "Unit_Price",
  "tolerance": 0.01,
  "total_rows": 1000,
  "checked_rows": 0,
  "error_rows": 0,
  "error_pct": 0.0,
  "sample_errors": []
}
```

> `checked_rows` — rows where all three columns are non-null (and denominator ≠ 0 for `divide`). Rows with any null are excluded from the check.
> `sample_errors` — up to 5 example rows where the difference exceeds tolerance. Use `row_index` to locate them in the preview table.
> `error_pct` — percentage of checked rows that failed. `0.0` means the dataset is fully consistent within tolerance.
> This endpoint never writes to disk — safe to call freely.

---

### 6. Fix Formula Inconsistencies

Overwrite values in a target column for rows where the math doesn't add up — replacing the wrong value with one recomputed from trusted operand columns. Unlike `fill-derived` which only fills nulls, this overwrites **existing non-null values** that are mathematically inconsistent.

Use this after `validate-formula` detects errors. The typical pattern is: **trust two columns, recompute the third.**

- **Endpoint**: `POST /datalab/fix-formula/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `target` | string | Yes | — | Column whose wrong values should be overwritten |
| `formula` | string | Yes | — | `"divide"`, `"multiply"`, `"add"`, `"subtract"` |
| `operand_a` | string | Yes | — | Trusted left-hand column |
| `operand_b` | string | Yes | — | Trusted right-hand column |
| `tolerance` | number | No | `0.01` | Rows within this threshold are considered correct and left untouched |

The fix is applied as: `target = operand_a <formula> operand_b` — but **only for rows** where the current `target` value differs from the formula result by more than `tolerance`.

**Fix `Unit_Price` by trusting `Total_Price` and `Quantity`:**
```json
{
  "target": "Unit_Price",
  "formula": "divide",
  "operand_a": "Total_Price",
  "operand_b": "Quantity",
  "tolerance": 0.01
}
```

#### Responses

- **Response (200)** — inconsistencies fixed:
```json
{
  "target": "Unit_Price",
  "formula": "divide",
  "operand_a": "Total_Price",
  "operand_b": "Quantity",
  "tolerance": 0.01,
  "cells_fixed": 14
}
```

- **Response (200)** — no inconsistencies found (no file write occurs):
```json
{
  "target": "Unit_Price",
  "formula": "divide",
  "operand_a": "Total_Price",
  "operand_b": "Quantity",
  "tolerance": 0.01,
  "cells_fixed": 0,
  "detail": "No inconsistent rows found within the given tolerance."
}
```

- **Response (400)** — non-numeric columns:
```json
{ "detail": "All three columns must be numeric: ['Unit_Price']" }
```

> This only touches rows where all three columns are non-null and (for `divide`) `operand_b != 0`.
> Rows that are already consistent within `tolerance` are left unchanged.
> Integer-typed target columns are auto-rounded after recomputation.
> After fixing, run `validate-formula` again with the same params to confirm `error_rows === 0`.

---

### 7. Cast Column Dtypes

Cast one or more columns to a new dtype. The change is persisted back to the dataset file on disk. Use this after `inspect` reveals columns with wrong types (e.g. `Date` as `object` instead of `datetime64`).

- **Endpoint**: `POST /datalab/cast/{dataset_id}/`
- **Auth Required**: Yes
- **Request Body**:
```json
{
  "casts": {
    "Date": "datetime",
    "Quantity": "integer",
    "Unit_Price": "float"
  }
}
```

**Supported target types:**

| Type | Pandas operation | Use when |
|---|---|---|
| `datetime` | `pd.to_datetime(errors='coerce')` | Column contains dates/timestamps stored as strings |
| `numeric` | `pd.to_numeric(errors='coerce')` | Column contains numbers stored as strings (keeps float) |
| `float` | `pd.to_numeric(errors='coerce')` | Same as numeric, explicit float output |
| `integer` | `pd.to_numeric(errors='coerce').astype('Int64')` | Whole numbers; supports nulls via nullable Int64 |
| `string` | `.astype(str)` | Force everything to string — ⚠️ null values become the literal string `"nan"` |
| `boolean` | `.astype(bool)` | Convert truthy/falsy values |
| `category` | `.astype('category')` | Low-cardinality string columns |

> Values that cannot be converted are coerced to `null` (NaT for datetime, NaN for numeric) rather than raising an error.

- **Response (200 OK)** — all casts succeeded:
```json
{
  "partial_failure": false,
  "updated_columns": [
    { "column": "Date",       "from_dtype": "object", "to_dtype": "datetime64[ns]", "status": "ok" },
    { "column": "Quantity",   "from_dtype": "object", "to_dtype": "Int64",          "status": "ok" },
    { "column": "Unit_Price", "from_dtype": "object", "to_dtype": "float64",        "status": "ok" }
  ]
}
```

- **Response (200 OK)** — partial success (`partial_failure: true` when at least one column succeeded and at least one failed):
```json
{
  "partial_failure": true,
  "updated_columns": [
    { "column": "Date",   "from_dtype": "object", "to_dtype": "datetime64[ns]", "status": "ok" },
    { "column": "Amount", "from_dtype": "object", "to_dtype": null,             "status": "error", "detail": "could not convert string to float" }
  ]
}
```

> If a column cast fails, `status` will be `"error"` and `to_dtype` will be `null`. Other columns in the same request that succeeded are still persisted.
> Casting to `"string"` when the column has null values returns a `"warning"` status — nulls become the literal string `"nan"`. Use `force: true` to proceed anyway.

**Warning response** (returned as `400` when warnings exist and `force` is not set):
```json
{
  "detail": "Some conversions are risky. Use 'force: true' to proceed.",
  "warnings": [
    { "column": "Name", "warning": "3 null value(s) will become the literal string 'nan'." }
  ],
  "validation_errors": []
}
```
> `validation_errors` lists columns that cannot be cast at all (hard errors). `warnings` lists risky-but-possible conversions. Both can be non-empty at the same time. To proceed despite warnings, resubmit with `"force": true` — hard errors in `validation_errors` are always skipped regardless of `force`.
> Successful casts are recorded in the activity log with `action: "CAST"` and `details: { columns: { col: type } }`.
> `dataset.file_size` is synced after every successful cast.

- **Response (422 Unprocessable Entity)** — every requested cast failed (nothing was persisted):
```json
{
  "detail": "All requested casts failed.",
  "updated_columns": [
    { "column": "Name", "target": "integer", "status": "error", "detail": "invalid literal for int() with base 10: 'Alice'" }
  ]
}
```

- **Response (400)** — unknown column:
```json
{ "detail": "Columns not found in dataset: ['BadCol']" }
```
- **Response (400)** — unsupported type:
```json
{ "detail": "Unsupported types: ['text']. Supported: ['boolean', 'category', 'datetime', 'float', 'integer', 'numeric', 'string']" }
```
---

### 8. Drop Duplicate Rows

Remove duplicate rows from the dataset and persist the result to disk. Choose a `mode` to control which rows are compared and which are kept.

- **Endpoint**: `POST /datalab/drop-duplicates/{dataset_id}/`
- **Auth Required**: Yes

#### Modes

| Mode | subset | keep | Behaviour |
|---|---|---|---|
| `"all_first"` | — | — | Compare all columns, keep first occurrence of each duplicate |
| `"all_last"` | — | — | Compare all columns, keep last occurrence of each duplicate |
| `"subset_keep"` | required | required | Compare only the listed columns, keep first or last match |
| `"drop_all"` | optional | — | Remove every copy of any duplicate row — no survivors |

#### Request Body

**Mode `all_first`** (default — can omit body entirely):
```json
{ "mode": "all_first" }
```

**Mode `all_last`**:
```json
{ "mode": "all_last" }
```

**Mode `subset_keep`** — dedupe by specific columns, keep first or last:
```json
{
  "mode": "subset_keep",
  "subset": ["transaction_id", "product_id"],
  "keep": "first"
}
```

**Mode `drop_all`** — remove every row that has any duplicate (optional subset):
```json
{
  "mode": "drop_all",
  "subset": ["email"]
}
```

#### Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | `"all_first"` \| `"all_last"` \| `"subset_keep"` \| `"drop_all"` | No | Dedup strategy. Defaults to `"all_first"`. |
| `subset` | array of strings | Only for `subset_keep` | Columns to compare. Optional for `drop_all` (omit = all columns). |
| `keep` | `"first"` \| `"last"` | Only for `subset_keep` | Which occurrence to keep. Defaults to `"first"`. |

- **Response (200 OK)** — duplicates found and removed:
```json
{
  "mode": "subset_keep",
  "rows_before": 1000,
  "rows_after": 950,
  "rows_dropped": 50
}
```

- **Response (200 OK)** — no duplicates found (file unchanged):
```json
{
  "rows_before": 1000,
  "rows_after": 1000,
  "rows_dropped": 0,
  "detail": "No duplicate rows found."
}
```

- **Response (400)** — invalid mode:
```json
{ "detail": "Invalid 'mode'. Choose one of: ['all_first', 'all_last', 'subset_keep', 'drop_all']" }
```
- **Response (400)** — `subset_keep` missing `subset`:
```json
{ "detail": "'subset' is required for mode 'subset_keep'." }
```
- **Response (400)** — `subset_keep` invalid `keep`:
```json
{ "detail": "For mode 'subset_keep', 'keep' must be 'first' or 'last'." }
```
- **Response (400)** — unknown column in `subset`:
```json
{ "detail": "Columns not found in dataset: ['bad_col']" }
```
- **Response (400)** — `subset` not a list of strings:
```json
{ "detail": "'subset' must be a non-empty list of column names." }
```

> When duplicates are dropped, `dataset.file_size` is updated automatically to reflect the smaller file.
> The cached DataFrame is invalidated so the next preview/inspect call returns the cleaned data.

---

### 9. Rename Column Header

Rename a single column header and persist the change to disk. If the column had a stored dtype cast, the cast is automatically migrated to the new name.

- **Endpoint**: `POST /datalab/rename-column/{dataset_id}/`
- **Auth Required**: Yes
- **Request Body**:
```json
{
  "old_name": "Unnamed: 0",
  "new_name": "product_id"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `old_name` | string | Yes | Current column name |
| `new_name` | string | Yes | Desired column name |

- **Response (200 OK)**:
```json
{
  "old_name": "Unnamed: 0",
  "new_name": "product_id",
  "columns": ["product_id", "name", "price", "quantity"]
}
```

> `columns` is the full updated column list in original order — use it to refresh the column headers in the UI.
> Rename is recorded in the activity log with `action: "RENAME_COLUMN"` and `details: { old_name, new_name }`.
> `dataset.file_size` is synced after every rename.

- **Response (400)** — column not found:
```json
{ "detail": "Column 'Unnamed: 0' not found in dataset." }
```
- **Response (400)** — name already taken:
```json
{ "detail": "Column 'product_id' already exists in dataset." }
```
- **Response (400)** — identical names:
```json
{ "detail": "New name is identical to the current name." }
```

---

### 10. Update Cell Value

Edit a single cell at a specific row and column. The value is coerced to match the column's existing dtype — if it can't be converted, a `400` is returned before anything is written to disk.

- **Endpoint**: `PATCH /datalab/update-cell/{dataset_id}/`
- **Auth Required**: Yes
- **Request Body**:
```json
{
  "row_index": 4,
  "column": "Quantity",
  "value": 99
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `row_index` | int | Yes | 0-based row position from the current preview |
| `column` | string | Yes | Column name to edit |
| `value` | any \| `null` | Yes | New cell value. Send `null` to set the cell to NaN |

**Dtype coercion rules:**

| Column dtype | Accepted values | Rejected example |
|---|---|---|
| `int64` / `Int64` | Whole numbers (`99`, `"99"`) | `"hello"` |
| `float64` | Decimal numbers (`3.14`, `"3.14"`) | `"hello"` |
| `bool` | `true`, `false`, `"true"`, `"false"`, `"1"`, `"0"` | `"yes"` |
| `datetime64` | ISO date strings (`"2024-01-15"`) | `"not-a-date"` |
| `object` / `string` / `category` | Anything — coerced to string | — |

- **Response (200 OK)**:
```json
{
  "row_index": 4,
  "column": "Quantity",
  "value": 99
}
```
> For datetime columns, `value` is returned as an ISO 8601 string (e.g. `"2024-01-15T00:00:00"`).
> For `null` input, `value` is returned as `null`.

- **Response (400)** — wrong dtype:
```json
{ "detail": "Cannot assign 'hello' to column 'Quantity' (dtype: int64)." }
```
- **Response (400)** — row out of range:
```json
{ "detail": "Row index 9999 is out of range (dataset has 1000 rows)." }
```
- **Response (400)** — column not found:
```json
{ "detail": "Column 'Quantity' not found in dataset." }
```

> Every successful cell edit is recorded in the activity log with `action: "UPDATE_CELL"` and `details: { row_index, column, value }`.
> `dataset.file_size` is synced after every successful cell edit.
> Always use `row_index` values from the **current** preview response — row positions shift after operations like drop_duplicates.

---

### 11. Replace Values

Replace specific sentinel or garbage values (e.g. `"N/A"`, `"-"`, `"?"`) with `null` (NaN) or any other value, across all columns or a targeted subset.

- **Endpoint**: `POST /datalab/replace-values/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `replacements` | object | Yes | Map of `{ "old_value": new_value }`. Use `null` as the new value to convert to NaN. |
| `columns` | array of strings | No | Columns to apply replacements to. Omit to apply across all columns. |

**Replace common sentinel strings with NaN (all columns):**
```json
{
  "replacements": { "N/A": null, "-": null, "?": null, "none": null, "null": null }
}
```

**Replace a specific value in targeted columns only:**
```json
{
  "replacements": { "999": null, "0": null },
  "columns": ["age", "salary"]
}
```

**Replace one value with another (not NaN):**
```json
{
  "replacements": { "Yes": "true", "No": "false" },
  "columns": ["is_active"]
}
```

#### Responses

- **Response (200)** — replacements applied:
```json
{
  "replacements": { "N/A": null, "-": null },
  "columns_affected": ["name", "email", "country"],
  "cells_replaced": 47
}
```

- **Response (200)** — no matches found (no file write occurs):
```json
{
  "replacements": { "N/A": null },
  "columns_affected": ["name", "email"],
  "cells_replaced": 0,
  "detail": "No matching values found."
}
```

- **Response (400)** — missing or invalid `replacements`:
```json
{ "detail": "'replacements' must be an object mapping old values to new values." }
```

- **Response (400)** — column not found:
```json
{ "detail": "Columns not found in dataset: ['unknown_col']" }
```

> Run `replace_values` **before** `fill_nulls` or `drop_nulls` — real-world CSVs often contain
> string sentinels (`"N/A"`, `"-"`) that pandas does not recognise as NaN, causing fill/drop
> operations to silently miss them.
> When replacements are applied, `dataset.file_size` is updated automatically to reflect the new file.

---

### 12. Drop Nulls

Drop rows or entire columns that contain null values. Covers two axes in one endpoint.

- **Endpoint**: `POST /datalab/drop-nulls/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `axis` | string | No | `"rows"` (default) or `"columns"` |
| `how` | string | No | Rows only — `"any"` (default) or `"all"` |
| `subset` | array of strings | No | Rows only — check nulls only in these columns |
| `thresh_pct` | number (0–100) | Columns only | Drop columns whose null % exceeds this threshold |

**Drop rows where ANY column is null:**
```json
{ "axis": "rows", "how": "any" }
```

**Drop rows where ALL columns are null:**
```json
{ "axis": "rows", "how": "all" }
```

**Drop rows where a key column is null:**
```json
{ "axis": "rows", "how": "any", "subset": ["user_id", "transaction_date"] }
```

**Drop columns with more than 70% null values:**
```json
{ "axis": "columns", "thresh_pct": 70 }
```

#### Responses

- **Response (200)** — rows dropped:
```json
{
  "axis": "rows",
  "rows_before": 1000,
  "rows_after": 943,
  "rows_dropped": 57
}
```

- **Response (200)** — columns dropped:
```json
{
  "axis": "columns",
  "columns_before": 12,
  "columns_after": 9,
  "columns_dropped": ["notes", "legacy_id", "deprecated_field"]
}
```

- **Response (200)** — nothing matched (no file write occurs):
```json
{
  "axis": "rows",
  "rows_before": 1000,
  "rows_after": 1000,
  "rows_dropped": 0,
  "detail": "No null rows/columns matched the criteria."
}
```

- **Response (400)** — missing `thresh_pct` for column axis:
```json
{ "detail": "'thresh_pct' is required when axis is 'columns'." }
```

- **Response (400)** — invalid `how`:
```json
{ "detail": "'how' must be 'any' or 'all'." }
```

> When dropping columns, `column_casts` entries for removed columns are not automatically
> cleaned up — they are silently ignored on next load since `apply_stored_casts` skips missing columns.
> Re-fetch `inspect` after this operation as column count will have changed.

---

### 13. Fill Nulls

Fill missing (NaN) values using a chosen imputation strategy. Apply to all columns or a targeted subset.

- **Endpoint**: `POST /datalab/fill-nulls/{dataset_id}/`
- **Auth Required**: Yes

#### Strategies

| Strategy | Description | Applies to |
|---|---|---|
| `constant` | Fill with a literal value (requires `value` field) | Any dtype |
| `mean` | Fill with column mean | Numeric only |
| `median` | Fill with column median (robust to outliers) | Numeric only |
| `mode` | Fill with most frequent value | Any dtype |
| `ffill` | Forward fill — use the previous row's value | Any dtype |
| `bfill` | Backward fill — use the next row's value | Any dtype |

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `strategy` | string | Yes | One of the strategies above |
| `value` | any | When `strategy` is `"constant"` | The literal fill value |
| `columns` | array of strings | No | Columns to fill. Omit to apply to all columns. |

**Fill all nulls with median (numeric columns only):**
```json
{ "strategy": "median" }
```

**Fill a categorical column with a constant:**
```json
{
  "strategy": "constant",
  "value": "Unknown",
  "columns": ["country", "status"]
}
```

**Forward-fill a time-series column:**
```json
{
  "strategy": "ffill",
  "columns": ["daily_price"]
}
```

**Fill numeric nulls with mean across specific columns:**
```json
{
  "strategy": "mean",
  "columns": ["age", "salary", "score"]
}
```

#### Responses

- **Response (200)** — nulls filled:
```json
{
  "strategy": "median",
  "cells_filled": 143,
  "skipped_columns": ["name", "country"]
}
```
> `skipped_columns` — columns that were skipped because the strategy is incompatible with their dtype
> (e.g. `mean`/`median` on a string column). No error is raised — they are silently skipped and reported here.

- **Response (200)** — nothing to fill (no file write occurs):
```json
{
  "strategy": "mean",
  "cells_filled": 0,
  "skipped_columns": [],
  "detail": "No null values found to fill."
}
```

- **Response (400)** — invalid strategy:
```json
{ "detail": "'strategy' must be one of: ['bfill', 'constant', 'ffill', 'mean', 'median', 'mode']" }
```

- **Response (400)** — missing `value` for constant strategy:
```json
{ "detail": "'value' is required when strategy is 'constant'." }
```

> Recommended order: `replace_values` → `drop_nulls` → `fill_nulls`.
> Run `replace_values` first so sentinel strings (`"N/A"`, `"-"`) become real NaN before fill strategies are applied.
> When nulls are filled, `dataset.file_size` is updated automatically to reflect the new file.

---

### 14. Detect Outliers

Scan one or more numeric columns for outliers using IQR or Z-Score and return per-column stats with sample rows. **Read-only — does not modify the dataset.**

- **Endpoint**: `GET /datalab/detect-outliers/{dataset_id}/`
- **Auth Required**: Yes

#### Query Parameters

| Param | Type | Default | Description |
|---|---|---|---|
| `columns` | string | — | **Required.** Comma-separated list of numeric column names to inspect |
| `method` | string | `"iqr"` | Detection method: `"iqr"` or `"zscore"` |
| `threshold` | number | `1.5` (IQR) / `3.0` (Z-Score) | Sensitivity (0–10). Lower = more outliers flagged |

**Method reference:**

| Method | How it works | Threshold meaning |
|---|---|---|
| `iqr` | Outlier if value < Q1 − t×IQR or > Q3 + t×IQR | Multiplier on IQR. `1.5` = standard; `3.0` = only extreme outliers |
| `zscore` | Outlier if \|z-score\| > threshold | Standard deviations from mean. `3.0` = standard; `2.0` = stricter |

**Detect outliers in `unit_price` and `quantity` using IQR:**
```
GET /datalab/detect-outliers/15/?columns=unit_price,quantity&method=iqr&threshold=1.5
```

**Detect using Z-Score with strict threshold:**
```
GET /datalab/detect-outliers/15/?columns=salary&method=zscore&threshold=2.5
```

#### Response (200 OK)
```json
{
  "dataset_id": 15,
  "method": "iqr",
  "threshold": 1.5,
  "columns": {
    "unit_price": {
      "outlier_count": 8,
      "outlier_pct": 0.8,
      "lower_bound": 2.125,
      "upper_bound": 49.875,
      "min": -5.0,
      "max": 210.0,
      "mean": 24.3,
      "median": 22.5,
      "sample_outliers": [
        { "row_index": 12, "unit_price": -5.0 },
        { "row_index": 47, "unit_price": 210.0 }
      ]
    },
    "quantity": {
      "outlier_count": 3,
      "outlier_pct": 0.3,
      "lower_bound": 0.0,
      "upper_bound": 18.0,
      "min": 1,
      "max": 500,
      "mean": 8.7,
      "median": 7.0,
      "sample_outliers": [
        { "row_index": 201, "quantity": 500 }
      ]
    }
  }
}
```

- **Response (400)** — missing columns:
```json
{ "detail": "'columns' is required." }
```
- **Response (400)** — non-numeric column:
```json
{ "detail": "Columns must be numeric: ['product_name']" }
```
- **Response (400)** — invalid method:
```json
{ "detail": "'method' must be one of: ['iqr', 'zscore']" }
```

> `lower_bound` / `upper_bound` — the computed fence values. Values outside this range are flagged as outliers.
> `sample_outliers` — up to 5 example rows. Use `row_index` to locate them in the preview table.
> This endpoint is safe to call freely — it never writes to disk.

---

### 15. Trim Outliers (Deletion)

Delete rows where any of the target columns contains an outlier. Use this when you are certain the values are measurement errors and the affected rows are a small fraction of your data.

- **Endpoint**: `POST /datalab/trim-outliers/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | array of strings | Yes | — | Numeric columns to check for outliers |
| `method` | string | No | `"iqr"` | `"iqr"` or `"zscore"` |
| `threshold` | number | No | `1.5` | Detection sensitivity (0–10, see Detect Outliers) |

```json
{
  "columns": ["unit_price", "quantity"],
  "method": "iqr",
  "threshold": 1.5
}
```

#### Responses

- **Response (200)** — rows deleted:
```json
{
  "columns": ["unit_price", "quantity"],
  "method": "iqr",
  "threshold": 1.5,
  "rows_before": 1000,
  "rows_after": 991,
  "rows_dropped": 9
}
```

- **Response (200)** — no outliers found (no file write occurs):
```json
{
  "columns": ["unit_price"],
  "method": "iqr",
  "threshold": 1.5,
  "rows_before": 1000,
  "rows_after": 1000,
  "rows_dropped": 0,
  "detail": "No outlier rows found."
}
```

> A row is dropped if **any** of the listed columns is an outlier for that row.
> Run `detect-outliers` first to preview how many rows will be removed before committing.
> Risk: information is permanently lost if the outlier was a real, rare event — use `impute-outliers` or `cap-outliers` instead when in doubt.

---

### 16. Impute Outliers (Replacement)

Replace outlier values in-place with the column's mean, median, or mode. The row is kept — only the offending value is replaced. Use this when you want to preserve the row but the specific value is clearly wrong.

- **Endpoint**: `POST /datalab/impute-outliers/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | array of strings | Yes | — | Numeric columns to impute |
| `method` | string | No | `"iqr"` | `"iqr"` or `"zscore"` |
| `threshold` | number | No | `1.5` | Detection sensitivity (0–10) |
| `strategy` | string | No | `"median"` | Replacement value: `"mean"`, `"median"`, or `"mode"` |

**Replace negative prices with the column median:**
```json
{
  "columns": ["unit_price"],
  "method": "iqr",
  "threshold": 1.5,
  "strategy": "median"
}
```

**Replace extreme salary values with the mean:**
```json
{
  "columns": ["salary"],
  "method": "zscore",
  "threshold": 3.0,
  "strategy": "mean"
}
```

#### Responses

- **Response (200)** — outliers replaced:
```json
{
  "columns": ["unit_price"],
  "method": "iqr",
  "threshold": 1.5,
  "strategy": "median",
  "cells_imputed": 8
}
```

- **Response (200)** — no outliers found (no file write occurs):
```json
{
  "columns": ["unit_price"],
  "method": "iqr",
  "threshold": 1.5,
  "strategy": "median",
  "cells_imputed": 0,
  "detail": "No outliers found."
}
```

- **Response (400)** — invalid strategy:
```json
{ "detail": "'strategy' must be one of: ['mean', 'median', 'mode']" }
```

> `median` is the recommended default — it is robust to the very outliers being replaced, unlike `mean` which can itself be pulled by extreme values.
> Integer-typed columns are auto-rounded after imputation.
> The replacement value is computed from all non-null values in the column, including non-outlier rows.

---

### 17. Cap Outliers / Winsorization

Instead of deleting or replacing, cap extreme values at a chosen percentile boundary. Values below the lower percentile are set to that percentile's value; values above the upper percentile are set to the upper percentile's value. This keeps the data distribution meaningful without letting extremes distort aggregates.

- **Endpoint**: `POST /datalab/cap-outliers/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | array of strings | Yes | — | Numeric columns to winsorize |
| `lower_pct` | number (0–100) | No | `5.0` | Lower percentile floor (e.g. `5` = 5th percentile) |
| `upper_pct` | number (0–100) | No | `95.0` | Upper percentile ceiling (e.g. `95` = 95th percentile) |

**Cap at 5th / 95th percentile (standard winsorization):**
```json
{
  "columns": ["unit_price", "salary"],
  "lower_pct": 5,
  "upper_pct": 95
}
```

**Tighter cap — only the top and bottom 1%:**
```json
{
  "columns": ["transaction_amount"],
  "lower_pct": 1,
  "upper_pct": 99
}
```

#### Responses

- **Response (200)** — values capped:
```json
{
  "columns": ["unit_price", "salary"],
  "lower_pct": 5.0,
  "upper_pct": 95.0,
  "cells_capped": 42
}
```

- **Response (200)** — all values already within bounds (no file write occurs):
```json
{
  "columns": ["unit_price"],
  "lower_pct": 5.0,
  "upper_pct": 95.0,
  "cells_capped": 0,
  "detail": "No values outside the percentile bounds."
}
```

- **Response (400)** — invalid percentile range:
```json
{ "detail": "'lower_pct' and 'upper_pct' must be numbers where 0 <= lower_pct < upper_pct <= 100." }
```

> Unlike trimming, no rows are deleted — the shape of the dataset is preserved.
> `cells_capped` is the total count across all columns — values that were already exactly at the boundary are not counted.
> After capping, run `describe` to confirm the new min/max values look correct.

---

### 18. Transform Column

Apply a mathematical transformation to one or more numeric columns. Useful for right-skewed data (many small values, a few very large ones) — a log transform pulls the distribution closer to normal and reduces the influence of extreme values.

- **Endpoint**: `POST /datalab/transform-column/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | array of strings | Yes | — | Numeric columns to transform |
| `function` | string | No | `"log"` | Transformation to apply: `"log"`, `"sqrt"`, or `"cbrt"` |

**Function reference:**

| Function | Formula | Requirement | Use when |
|---|---|---|---|
| `log` | `ln(x)` | All values must be **> 0** | Right-skewed data (sales, income, counts) |
| `sqrt` | `√x` | All values must be **≥ 0** | Moderate skew; count data |
| `cbrt` | `∛x` | No restriction — works with negatives | When `log` / `sqrt` won't apply due to zeros or negatives |

**Log-transform sales and revenue (right-skewed):**
```json
{
  "columns": ["sales_amount", "revenue"],
  "function": "log"
}
```

**Square-root transform count columns:**
```json
{
  "columns": ["page_views", "click_count"],
  "function": "sqrt"
}
```

#### Responses

- **Response (200)** — columns transformed:
```json
{
  "function": "log",
  "transformed_columns": ["sales_amount", "revenue"],
  "skipped_columns": []
}
```

- **Response (200)** — some columns skipped due to invalid values:
```json
{
  "function": "log",
  "transformed_columns": ["revenue"],
  "skipped_columns": [
    { "column": "sales_amount", "reason": "log requires all values > 0" }
  ]
}
```

- **Response (200)** — all columns skipped (no file write occurs):
```json
{
  "function": "log",
  "transformed_columns": [],
  "skipped_columns": [
    { "column": "sales_amount", "reason": "log requires all values > 0" }
  ],
  "detail": "No columns were transformed."
}
```

- **Response (400)** — invalid function:
```json
{ "detail": "'function' must be one of: ['log', 'sqrt', 'cbrt']" }
```

> Transformation is applied to the entire column including non-outlier values — this is a column-wide reshape, not an outlier fix.
> Columns with any value that violates the function's constraint are skipped entirely (not partially transformed) and reported in `skipped_columns`.
> After transforming, run `describe` to verify the new distribution looks as expected.
> **This operation is irreversible** — duplicate the dataset first if you need to compare before/after.

---

### 19. Drop Columns

Permanently remove one or more columns from the dataset. Stored dtype casts for dropped columns are automatically cleaned up.

- **Endpoint**: `POST /datalab/drop-columns/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `columns` | array of strings | Yes | Column names to drop |

```json
{ "columns": ["legacy_id", "notes", "Unnamed: 0"] }
```

#### Responses

- **Response (200)** — columns dropped:
```json
{
  "columns_dropped": ["legacy_id", "notes", "Unnamed: 0"],
  "remaining_columns": ["user_id", "name", "salary", "date"]
}
```

- **Response (400)** — column not found:
```json
{ "detail": "Columns not found in dataset: ['bad_col']" }
```

> `remaining_columns` is the full list of columns still in the dataset — use it to refresh the column display in the UI.
> After dropping, re-fetch `inspect` to update null counts and memory usage.
> **This is irreversible** — duplicate the dataset first if unsure.

---

### 20. Add Derived Column

Create a new column by computing `operand_a <formula> operand_b` across every row. Unlike `fill-derived` (which only fills nulls in an existing column), this always creates a brand-new column.

- **Endpoint**: `POST /datalab/add-column/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `new_name` | string | Yes | Name for the new column |
| `formula` | string | Yes | `"divide"`, `"multiply"`, `"add"`, `"subtract"` |
| `operand_a` | string | Yes | Left-hand column (must be numeric) |
| `operand_b` | string | Yes | Right-hand column (must be numeric) |

**Create a `profit_margin` column from `profit ÷ revenue`:**
```json
{
  "new_name": "profit_margin",
  "formula": "divide",
  "operand_a": "profit",
  "operand_b": "revenue"
}
```

**Create a `total_price` column from `quantity × unit_price`:**
```json
{
  "new_name": "total_price",
  "formula": "multiply",
  "operand_a": "quantity",
  "operand_b": "unit_price"
}
```

#### Responses

- **Response (200)** — column added:
```json
{
  "new_column": "profit_margin",
  "formula": "divide",
  "operand_a": "profit",
  "operand_b": "revenue",
  "total_columns": 9
}
```

- **Response (400)** — column name already exists:
```json
{ "detail": "Column 'profit_margin' already exists. Use rename-column or choose a different name." }
```

- **Response (400)** — non-numeric operand:
```json
{ "detail": "Operand columns must be numeric: ['revenue']" }
```

> For `divide`, rows where `operand_b` is `0` produce `null` (not an error).
> Both operand columns must be numeric. The new column is always appended as the last column.

---

### 21. Filter Rows

Keep only the rows that match a condition and discard the rest. This permanently removes rows from the dataset — use `detect-outliers` or `preview` to audit before committing.

- **Endpoint**: `POST /datalab/filter-rows/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `column` | string | Yes | Column to apply the filter condition to |
| `operator` | string | Yes | Comparison operator (see table below) |
| `value` | any | Depends | The value to compare against. Not required for `isnull` / `notnull`. |

**Operator reference:**

| Operator | Meaning | Example use |
|---|---|---|
| `eq` | Equal to | Keep rows where `status == "active"` |
| `ne` | Not equal to | Remove rows where `country == "Unknown"` |
| `gt` | Greater than | Keep rows where `age > 18` |
| `gte` | Greater than or equal | Keep rows where `salary >= 30000` |
| `lt` | Less than | Keep rows where `score < 100` |
| `lte` | Less than or equal | Keep rows where `discount <= 50` |
| `contains` | String contains (case-sensitive) | Keep rows where `email` contains `"@gmail"` |
| `not_contains` | String does not contain | Remove rows where `notes` contains `"test"` |
| `isnull` | Value is null | Keep only rows with missing `phone_number` |
| `notnull` | Value is not null | Drop rows where `user_id` is missing |

**Keep only active users:**
```json
{ "column": "status", "operator": "eq", "value": "active" }
```

**Remove rows where salary is zero or missing:**
```json
{ "column": "salary", "operator": "gt", "value": 0 }
```

**Keep only rows with a valid email:**
```json
{ "column": "email", "operator": "notnull" }
```

#### Responses

- **Response (200)** — rows removed:
```json
{
  "column": "status",
  "operator": "eq",
  "value": "active",
  "rows_before": 1000,
  "rows_after": 742,
  "rows_removed": 258
}
```

- **Response (200)** — no rows removed (all matched the filter):
```json
{
  "column": "status",
  "operator": "eq",
  "value": "active",
  "rows_before": 1000,
  "rows_after": 1000,
  "rows_removed": 0,
  "detail": "No rows were removed — all rows matched the filter."
}
```

- **Response (400)** — invalid operator:
```json
{ "detail": "Invalid 'operator'. Choose one of: ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'not_contains', 'isnull', 'notnull']" }
```

- **Response (400)** — value missing:
```json
{ "detail": "'value' is required for operator 'eq'." }
```

> Row indices reset to 0-based after filtering — always re-fetch `preview` before using `update-cell`.
> `contains` / `not_contains` perform a literal string search (not regex). All values are cast to string before matching.

---

### 22. Clean String Columns

Apply a string-cleaning operation to one or more text columns. Useful for normalizing inconsistent user-entered data before analysis.

- **Endpoint**: `POST /datalab/clean-string/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `columns` | array of strings | Yes | Text columns to clean (must be object/string dtype) |
| `operation` | string | Yes | Operation to apply (see table below) |

**Operation reference:**

| Operation | What it does | Example: `" hello World "` → |
|---|---|---|
| `strip` | Remove leading and trailing whitespace | `"hello World"` |
| `lower` | Convert to all lowercase | `" hello world "` |
| `upper` | Convert to all uppercase | `" HELLO WORLD "` |
| `title` | Capitalize first letter of each word | `" Hello World "` |

**Strip whitespace from name columns:**
```json
{ "columns": ["first_name", "last_name"], "operation": "strip" }
```

**Normalize country values to title case:**
```json
{ "columns": ["country", "city"], "operation": "title" }
```

**Lowercase email addresses:**
```json
{ "columns": ["email"], "operation": "lower" }
```

#### Responses

- **Response (200)** — values changed:
```json
{
  "operation": "strip",
  "columns": ["first_name", "last_name"],
  "cells_changed": 34
}
```

- **Response (200)** — no changes (all values already clean):
```json
{
  "operation": "strip",
  "columns": ["email"],
  "cells_changed": 0,
  "detail": "No values were changed."
}
```

- **Response (400)** — non-text column:
```json
{ "detail": "String operations only apply to text columns: ['age']" }
```

> `cells_changed` counts only cells where the value actually changed — NaN values are not counted.
> Run `strip` before `lower` / `upper` / `title` if columns may have leading/trailing whitespace.

---

### 23. Scale (Normalize) Columns

Normalize numeric columns so values fall on a consistent scale. Essential before distance-based algorithms (KNN, clustering) or when combining columns with different units.

- **Endpoint**: `POST /datalab/scale-columns/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | array of strings | Yes | — | Numeric columns to scale |
| `method` | string | No | `"minmax"` | `"minmax"` or `"zscore"` |

**Method reference:**

| Method | Formula | Output range | Use when |
|---|---|---|---|
| `minmax` | `(x − min) / (max − min)` | `[0, 1]` | You need bounded output; values have no meaningful distribution |
| `zscore` | `(x − mean) / std` | Unbounded (mean=0, std=1) | Data is approximately normal; you need to compare across distributions |

**Min-max scale age and salary:**
```json
{
  "columns": ["age", "salary"],
  "method": "minmax"
}
```

**Z-score normalize before clustering:**
```json
{
  "columns": ["revenue", "units_sold", "avg_order_value"],
  "method": "zscore"
}
```

#### Responses

- **Response (200)** — columns scaled:
```json
{
  "method": "minmax",
  "scaled_columns": ["age", "salary"],
  "skipped_columns": []
}
```

- **Response (200)** — some columns skipped:
```json
{
  "method": "minmax",
  "scaled_columns": ["salary"],
  "skipped_columns": [
    { "column": "status_code", "reason": "all values identical — cannot min-max scale" }
  ]
}
```

- **Response (200)** — all skipped (no file write):
```json
{
  "method": "minmax",
  "scaled_columns": [],
  "skipped_columns": [...],
  "detail": "No columns were scaled."
}
```

> `minmax` skips columns where all values are identical (division by zero).
> `zscore` skips columns where `std = 0` (all values are the same).
> **This is irreversible** — the original scale is lost. Duplicate the dataset first if you need to compare pre/post.
> After scaling, run `describe` to verify that `min`, `max`, `mean`, and `std` look correct.

---

### 24. Extract Datetime Features

Parse a datetime column and extract sub-fields (year, month, day, etc.) into new integer columns. Useful for making temporal patterns accessible to ML models that cannot use raw timestamps.

- **Endpoint**: `POST /datalab/extract-datetime/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `column` | string | Yes | Source datetime column to parse |
| `features` | array of strings | Yes | Sub-fields to extract (see table below) |

**Available features:**

| Feature | New column name | Values |
|---|---|---|
| `year` | `{column}_year` | e.g. `2024` |
| `month` | `{column}_month` | `1`–`12` |
| `day` | `{column}_day` | `1`–`31` |
| `weekday` | `{column}_weekday` | `0` (Monday) – `6` (Sunday) |
| `hour` | `{column}_hour` | `0`–`23` |
| `minute` | `{column}_minute` | `0`–`59` |

**Extract year, month, and weekday from an order date:**
```json
{
  "column": "order_date",
  "features": ["year", "month", "weekday"]
}
```

**Extract all time components from a timestamp:**
```json
{
  "column": "created_at",
  "features": ["year", "month", "day", "hour", "minute"]
}
```

#### Responses

- **Response (200)** — features extracted:
```json
{
  "source_column": "order_date",
  "added_columns": ["order_date_year", "order_date_month", "order_date_weekday"],
  "total_columns": 12
}
```

- **Response (400)** — column not found:
```json
{ "detail": "Column 'order_date' not found in dataset." }
```

- **Response (400)** — output columns already exist:
```json
{ "detail": "Columns already exist: ['order_date_year']. Rename or drop them first." }
```

- **Response (400)** — invalid feature name:
```json
{ "detail": "Invalid features: ['quarter']. Choose from: ['year', 'month', 'day', 'weekday', 'hour', 'minute']" }
```

> The source column does not need to be already cast as `datetime` — the engine calls `pd.to_datetime(errors='coerce')` internally. Rows that cannot be parsed produce `null` in the new columns.
> New columns are always appended after the existing columns.
> The source column itself is not removed or modified.

---

### 25. Encode Categorical Columns

Encode string/categorical columns as numbers. Required before most ML algorithms that cannot handle text labels directly.

- **Endpoint**: `POST /datalab/encode-columns/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | array of strings | Yes | — | Columns to encode |
| `strategy` | string | No | `"label"` | `"label"` or `"onehot"` |

**Strategy reference:**

| Strategy | What it does | Output | Use when |
|---|---|---|---|
| `label` | Replaces each unique value with an integer (0-based) | Replaces the column in-place | Ordinal data or tree-based models |
| `onehot` | Creates one binary column per unique value; drops original | Adds N new columns | Nominal data; linear models |

**Label-encode a `status` column:**
```json
{ "columns": ["status"], "strategy": "label" }
```

**One-hot encode a `country` column:**
```json
{ "columns": ["country"], "strategy": "onehot" }
```

#### Responses

- **Response (200)** — label encoding:
```json
{
  "strategy": "label",
  "result": [
    {
      "column": "status",
      "strategy": "label",
      "mapping": { "active": 0, "inactive": 1, "pending": 2 }
    }
  ],
  "total_columns": 8
}
```

- **Response (200)** — one-hot encoding:
```json
{
  "strategy": "onehot",
  "result": [
    {
      "column": "country",
      "strategy": "onehot",
      "new_columns": ["country_Cambodia", "country_Thailand", "country_Vietnam"]
    }
  ],
  "total_columns": 11
}
```

- **Response (400)** — column not found:
```json
{ "detail": "Columns not found in dataset: ['bad_col']" }
```

> **Label encoding**: The integer assignment is based on order of first appearance (`pd.factorize`), not alphabetical. Save the `mapping` from the response if you need to reverse-decode later.
> **One-hot encoding**: The original column is dropped and replaced with binary indicator columns. Column names follow the pattern `{original_column}_{value}`. High-cardinality columns (hundreds of unique values) will create many new columns — check `total_columns` in the response.
> After one-hot encoding, re-fetch `inspect` as the column list has changed significantly.

---

### 26. Normalize Column Names

Rename all column headers to `lowercase_snake_case` — removes spaces, special characters, and mixed casing. Stored dtype casts are automatically migrated to the new names.

- **Endpoint**: `POST /datalab/normalize-column-names/{dataset_id}/`
- **Auth Required**: Yes
- **Request Body**: *(empty — no parameters needed)*

#### Responses

- **Response (200)** — columns renamed:
```json
{
  "renamed": {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Date Of Birth": "date_of_birth",
    "Total $$$": "total___"
  },
  "columns": ["user_id", "first_name", "last_name", "date_of_birth", "salary", "total___"]
}
```

- **Response (200)** — already normalized (no file write):
```json
{
  "detail": "All column names are already normalized.",
  "columns": ["user_id", "first_name", "salary"]
}
```

> `renamed` only includes columns that were actually changed — columns already in snake_case are omitted.
> `columns` is the full updated list in order — use it to refresh the column display.
> Special characters (spaces, `$`, `%`, `-`, etc.) are replaced with `_`. Leading/trailing underscores are stripped.
> Run this early in the cleaning pipeline — normalized names make all subsequent operations less error-prone.

---

### 27. Revert to Snapshot (Undo)

Replaces the current dataset file with a previous snapshot. This is used for "Undo" functionality (reverting the last mutation) or restoring the dataset to a specific point in time.

- **Endpoint**: `POST /datalab/revert/{dataset_id}/`
- **Auth Required**: Yes

#### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `undo` | boolean | No | If `true`, reverts to the most recent snapshot (the state before the last mutation) |
| `snapshot_id` | int | No | Revert to a specific snapshot by ID. |

> One of `undo: true` or `snapshot_id` must be provided.

**Perform "Undo":**
```json
{
  "undo": true
}
```

**Revert to specific snapshot:**
```json
{
  "snapshot_id": 42
}
```

#### Responses

- **Response (200 OK)**:
```json
{
  "detail": "Dataset reverted successfully.",
  "updated_at": "2026-05-04T08:15:00Z"
}
```

- **Response (400)** — no snapshots to undo:
```json
{ "detail": "No snapshots available to undo." }
```

- **Response (404)** — snapshot not found:
```json
{ "detail": "Not found." }
```

> **How Snapshots work**: PyAnalypt automatically creates a snapshot of the dataset **before** every mutating operation (Clean, Cast, Drop, etc.). These snapshots are stored as separate files. 
> Reverting overwrites the current file and invalidates the data cache.
> The `REVERT` action is logged in the activity logs.


---

## 📊 Exploratory Data Analysis (EDA)

All EDA endpoints are **read-only GET requests** — they never mutate the dataset file or write activity logs. Stored dtype casts (`column_casts`) are applied before analysis, so results reflect the user's intended column types.

**Base path**: `GET /api/v1/eda/`

---

### 1. Correlation Matrix

Compute pairwise correlation coefficients between numeric columns.

- **Endpoint**: `GET /eda/correlation/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `columns` | list | all numeric | Column names to include (repeatable: `?columns=a&columns=b`) |
| `method` | string | `pearson` | Correlation method: `pearson`, `spearman`, `kendall` |

#### Response (200 OK)
```json
{
  "columns": ["age", "salary", "score"],
  "method": "pearson",
  "matrix": [
    {"column": "age",    "values": {"age": 1.0, "salary": 0.7412, "score": -0.231}},
    {"column": "salary", "values": {"age": 0.7412, "salary": 1.0, "score": 0.182}},
    {"column": "score",  "values": {"age": -0.231, "salary": 0.182, "score": 1.0}}
  ]
}
```

> If no `columns` are provided, all numeric columns in the dataset are used automatically.
> Non-numeric columns listed in `columns` are rejected with a 400 error.

---

### 2. Categorical Association (Cramér's V)

Compute the strength of association between categorical columns using Cramér's V (ranges from 0 to 1). Useful for identifying relationships between non-numeric features.

- **Endpoint**: `GET /eda/association/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `columns` | list | all categorical | Column names to include (repeatable) |

#### Response (200 OK)
```json
{
  "columns": ["department", "gender", "performance_rating"],
  "method": "cramers_v",
  "matrix": [
    {"column": "department", "values": {"department": 1.0, "gender": 0.12, "performance_rating": 0.45}},
    {"column": "gender",     "values": {"department": 0.12, "gender": 1.0, "performance_rating": 0.05}}
  ]
}
```

> **Interpretation**: 0.0 = no association, 0.1 = weak, 0.3 = medium, 0.5+ = strong association.

---

### 3. Distribution

Histogram bin data, skewness, and kurtosis for numeric columns.

- **Endpoint**: `GET /eda/distribution/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `columns` | list | all numeric | Column names (repeatable) |
| `bins` | integer | `20` | Number of histogram bins (1–100) |

#### Response (200 OK)
```json
{
  "salary": {
    "count": 950,
    "mean": 55200.4,
    "std": 12300.1,
    "min": 20000.0,
    "max": 110000.0,
    "skewness": 0.8741,
    "kurtosis": 1.2305,
    "bins": [
      {"range_start": 20000.0, "range_end": 23000.0, "count": 12},
      {"range_start": 23000.0, "range_end": 26000.0, "count": 35}
    ]
  }
}
```

> Skewness > 1 (or < −1) indicates a significantly skewed distribution.
> Kurtosis > 3 indicates heavy tails; < 3 indicates thin tails compared to normal.

---

### 3. Value Counts

Frequency table showing how often each value appears in a column.

- **Endpoint**: `GET /eda/value-counts/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `columns` | list | first 50 columns | Column names (repeatable). Omitting on wide datasets returns the first 50 columns only. |
| `top_n` | integer | `20` | Maximum values to return per column (1–100) |

#### Response (200 OK)
```json
{
  "country": {
    "total_rows": 1000,
    "null_count": 5,
    "unique_count": 42,
    "top_values": [
      {"value": "Cambodia", "count": 340, "pct": 34.0},
      {"value": "Thailand", "count": 280, "pct": 28.0},
      {"value": null,       "count": 5,   "pct": 0.5}
    ]
  }
}
```

> `null` values are included in `top_values` so you can see the null distribution alongside valid values.
> Works for any column type — numeric, string, datetime, boolean.

---

### 4. Cross-tabulation

Two-way frequency table between two categorical columns.

- **Endpoint**: `GET /eda/crosstab/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `col_a` | string | *(required)* | Row-axis column |
| `col_b` | string | *(required)* | Column-axis column |
| `normalize` | `"true"` / `"false"` | `"false"` | Return row percentages instead of counts |

#### Response (200 OK) — counts
```json
{
  "gender": ["F", "M"],
  "department": ["Engineering", "Marketing", "Sales"],
  "normalize": false,
  "table": [
    {"gender": "F", "Engineering": 45, "Marketing": 78, "Sales": 32},
    {"gender": "M", "Engineering": 90, "Marketing": 41, "Sales": 67}
  ]
}
```

#### Response (200 OK) — normalized (`normalize=true`)
```json
{
  "normalize": true,
  "table": [
    {"gender": "F", "Engineering": 0.2903, "Marketing": 0.5032, "Sales": 0.2065}
  ]
}
```

> Columns with more than **50 unique values** are rejected with a 400 error — use `value-counts` to explore high-cardinality columns instead.
> `normalize=true` returns row-proportions (each row sums to 1.0).

---

### 5. Outlier Summary

Read-only aggregated outlier report across all numeric columns.

- **Endpoint**: `GET /eda/outlier-summary/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `method` | string | `iqr` | Detection method: `iqr` or `zscore` |
| `threshold` | float | `1.5` | IQR multiplier or Z-score cutoff (max: `10`) |

#### Response (200 OK)
```json
{
  "method": "iqr",
  "threshold": 1.5,
  "total_rows": 1000,
  "numeric_columns_checked": 5,
  "columns_with_outliers": 2,
  "total_outlier_cells": 34,
  "per_column": {
    "salary": {
      "outlier_count": 22,
      "outlier_pct": 2.2,
      "lower_bound": 18000.0,
      "upper_bound": 95000.0,
      "mean": 55200.4,
      "std": 12300.1
    },
    "age": {
      "outlier_count": 0,
      "outlier_pct": 0.0,
      "lower_bound": 18.0,
      "upper_bound": 72.0,
      "mean": 35.4,
      "std": 11.2
    }
  }
}
```

> This endpoint is read-only — use datalab endpoints (`/datalab/trim-outliers/`, `/datalab/cap-outliers/`, etc.) to actually treat outliers.

---

### 6. Missing Value Heatmap

Null pattern analysis: per-column null rates, worst rows, and co-null pairs.

- **Endpoint**: `GET /eda/missing-heatmap/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**: *(none)*

> For datasets with more than **50,000 rows**, the analysis is run on a random 50,000-row sample (seed=42). The `total_rows` field in the response reflects the sampled count, not the full dataset size.

#### Response (200 OK)
```json
{
  "total_rows": 1000,
  "total_columns": 8,
  "columns_with_nulls": 3,
  "per_column": {
    "salary":  {"null_count": 12, "null_pct": 1.2},
    "age":     {"null_count": 0,  "null_pct": 0.0},
    "address": {"null_count": 45, "null_pct": 4.5}
  },
  "worst_rows": [
    {"row_index": 142, "null_count": 3},
    {"row_index": 567, "null_count": 2}
  ],
  "co_null_pairs": {
    "salary × address": 0.712
  }
}
```

> `worst_rows` — up to 10 rows with the most null values, sorted descending. Use row_index with the `update-cell` endpoint to patch specific cells.
> `co_null_pairs` — column pairs with co-null correlation ≥ 0.5 (i.e., when one is null, the other tends to be too). Only shown for pairs with |r| ≥ 0.5.

---

### 7. Pairwise Scatter

X/Y point pairs for scatter plot visualization between two columns.

- **Endpoint**: `GET /eda/pairwise/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `col_x` | string | *(required)* | X-axis column — **must be numeric** |
| `col_y` | string | *(required)* | Y-axis column — **must be numeric** |
| `sample` | integer | `500` | Max points to return (1–5000) |

#### Response (200 OK)
```json
{
  "col_x": "age",
  "col_y": "salary",
  "total_valid_rows": 988,
  "sampled": 500,
  "pearson_r": 0.7412,
  "points": [
    {"x": 28, "y": 45000},
    {"x": 35, "y": 62000}
  ]
}
```

> Both `col_x` and `col_y` must be numeric columns — non-numeric columns are rejected with a 400 error.
> Only rows where **both** columns are non-null are included.
> When `total_valid_rows > sample`, the returned `points` are a random sample (seed=42 for reproducibility).
> `pearson_r` is computed on the **full** valid dataset (not the sample), so it reflects the true correlation even for large datasets.

---

## 📈 Visualization (ECharts)

All visualization endpoints return **Apache ECharts-ready `option` objects** — pass the response body directly to `echarts.setOption()`. All endpoints are read-only (`GET`) and require authentication.

**Base path**: `/api/v1/viz/`

> All endpoints return `{"detail": "..."}` on error. Ownership is enforced — datasets belonging to other users return 404.

---

### 1. Bar Chart

Aggregate a numeric column by a categorical column and return a bar chart option. Supports grouped bars via `group_by`.

- **Endpoint**: `GET /viz/bar/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x_col` | string | *(required)* | Categorical column for the X-axis |
| `y_col` | string | *(required)* | Numeric column to aggregate — **must be numeric** |
| `agg` | string | `sum` | Aggregation function: `sum`, `mean`, `count`, `min`, `max` |
| `group_by` | string | — | Optional second categorical column for grouped bars |
| `limit` | integer | `20` | Max number of X-axis categories to return (1–100) |

#### Response (200 OK)
```json
{
  "chart_type": "bar",
  "xAxis": { "type": "category", "name": "city", "data": ["New York", "London", "Tokyo"] },
  "yAxis": { "type": "value", "name": "sum(salary)" },
  "series": [
    { "name": "salary", "type": "bar", "data": [420000, 380000, 310000] }
  ]
}
```

**With `group_by`** — each group becomes its own series:
```json
{
  "chart_type": "bar",
  "xAxis": { "type": "category", "name": "city", "data": ["New York", "London"] },
  "yAxis": { "type": "value", "name": "sum(salary)" },
  "series": [
    { "name": "Engineering", "type": "bar", "data": [250000, 200000] },
    { "name": "Sales",       "type": "bar", "data": [170000, 180000] }
  ]
}
```

> Categories are ranked by total Y magnitude — the top `limit` are returned.
> When using `group_by`, up to 20 groups are included (ranked by total Y across all X categories).

---

### 2. Line Chart

Plot one or more numeric columns against an X-axis column. X can be datetime, numeric, or categorical — it is sorted ascending by default.

- **Endpoint**: `GET /viz/line/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x_col` | string | *(required)* | X-axis column (any type — datetime recommended) |
| `y_cols` | string[] | *(required)* | One or more numeric columns (repeat param: `y_cols=revenue&y_cols=cost`) |
| `sort` | boolean | `true` | Sort rows by `x_col` ascending before plotting |

#### Response (200 OK)
```json
{
  "chart_type": "line",
  "xAxis": { "type": "category", "name": "date", "data": ["2024-01", "2024-02", "2024-03"] },
  "yAxis": { "type": "value" },
  "series": [
    { "name": "revenue", "type": "line", "data": [12000, 15000, 13500] },
    { "name": "cost",    "type": "line", "data": [8000, 9000, 8500] }
  ]
}
```

> All `y_cols` must be numeric. `x_col` can be any type (datetime values are serialized as strings).
> Response is capped at **5 000 rows** — if the dataset is larger, only the first 5 000 (after sort) are returned.

---

### 3. Scatter Chart

X/Y scatter plot between two numeric columns. Supports series-level grouping via `color_by` and random sampling for large datasets.

- **Endpoint**: `GET /viz/scatter/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `col_x` | string | *(required)* | X-axis column — **must be numeric** |
| `col_y` | string | *(required)* | Y-axis column — **must be numeric** |
| `color_by` | string | — | Optional categorical column — splits into one series per group |
| `sample` | integer | `500` | Max points per series (1–5 000) |

#### Response (200 OK)
```json
{
  "chart_type": "scatter",
  "xAxis": { "type": "value", "name": "age" },
  "yAxis": { "type": "value", "name": "salary" },
  "pearson_r": 0.7412,
  "series": [
    {
      "name": "age vs salary",
      "type": "scatter",
      "data": [[28, 45000], [35, 62000], [42, 78000]]
    }
  ]
}
```

**With `color_by`** — one series per group:
```json
{
  "pearson_r": 0.7412,
  "series": [
    { "name": "Engineering", "type": "scatter", "data": [[28, 72000], [34, 85000]] },
    { "name": "Sales",       "type": "scatter", "data": [[31, 55000], [29, 48000]] }
  ]
}
```

> `pearson_r` is always computed on the **full** valid dataset before sampling.
> Only rows where both `col_x` and `col_y` are non-null are included.
> Sampling uses `random_state=42` for reproducible results.

---

### 4. Histogram

Distribution chart for one or more numeric columns. Returns ECharts bar options with bin ranges on the X-axis and counts on the Y-axis, plus descriptive stats per column.

- **Endpoint**: `GET /viz/histogram/{dataset_id}/`
- **Auth Required**: Yes
- **Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `columns` | string[] | *(all numeric)* | Columns to compute (repeat param: `columns=age&columns=salary`) |
| `bins` | integer | `20` | Number of histogram bins (1–100) |

#### Response (200 OK)

Response is a dict keyed by column name. Each value is a standalone ECharts option:
```json
{
  "age": {
    "chart_type": "histogram",
    "xAxis": {
      "type": "category",
      "name": "age",
      "data": ["18.0–26.0", "26.0–34.0", "34.0–42.0"]
    },
    "yAxis": { "type": "value", "name": "count" },
    "series": [
      { "name": "age", "type": "bar", "data": [42, 118, 95] }
    ],
    "stats": {
      "count": 988,
      "mean": 34.21,
      "std": 9.87,
      "min": 18.0,
      "max": 65.0,
      "skewness": 0.312,
      "kurtosis": -0.451
    }
  },
  "salary": { "..." }
}
```

> If `columns` is omitted, all numeric columns are returned.
> `stats` are computed on the non-null values only.
> Bin boundaries use `–` (en-dash) as separator: `"18.0–26.0"`.

---

## 🎯 Analysis Goals

The Analysis Goals module is the **starting point for every analysis workflow**. After uploading a dataset the analyst defines *why* they are analysing it (a problem statement) and breaks it into specific research questions — Q1, Q2, Q3...Qn.

Questions can be written manually or auto-generated by the local Ollama LLM from the dataset's column headers. The goal is then linked to the final Report so the exported PDF reflects the original analytical intent.

**Workflow position:** Upload Dataset → **Define Analysis Goal** → Datalab → EDA → Visualization → Report

**Base path**: `/api/v1/goals/`

> Ownership is enforced on every endpoint — goals belonging to other users always return 404.

---

### AnalysisGoal Object (detail)

| Field | Type | Description |
|---|---|---|
| `id` | int | Unique identifier |
| `dataset` | int | FK to the source dataset |
| `problem_statement` | string | The analyst's stated reason for this analysis |
| `question_count` | int | Number of questions under this goal |
| `questions` | array | Full list of `AnalysisQuestion` objects — only present on detail view |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last update timestamp |

### AnalysisGoal Object (list)

Same as above but **`questions` is omitted** — only `question_count` is returned.

### AnalysisQuestion Object

| Field | Type | Description |
|---|---|---|
| `id` | int | Unique identifier |
| `order` | int | Sort position (0-based, ascending) |
| `question` | string | The analytical question text |
| `source` | string | `"manual"` \| `"ai"` — how the question was created |
| `created_at` | datetime | When the question was added |

---

### 1. List Goals

Returns all analysis goals owned by the authenticated user, ordered newest first.

- **Endpoint**: `GET /goals/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
[
  {
    "id": 1,
    "dataset": 23,
    "problem_statement": "Why did Q3 revenue drop 18%?",
    "question_count": 3,
    "created_at": "2026-05-01T09:00:00Z",
    "updated_at": "2026-05-01T09:00:00Z"
  }
]
```

---

### 2. Create Goal

- **Endpoint**: `POST /goals/`
- **Auth Required**: Yes
- **Request Body**:

| Field | Required | Description |
|---|---|---|
| `dataset` | Yes | Dataset ID (must belong to the authenticated user) |
| `problem_statement` | No | Why you are analysing this dataset |

```json
{
  "dataset": 23,
  "problem_statement": "Why did Q3 revenue drop 18% compared to last year?"
}
```

- **Response (201 Created)**: Full `AnalysisGoal` object with `questions: []`.
- **Response (400)**: Dataset does not exist or belongs to another user.

> A dataset can have multiple goals — one per analysis session.

---

### 3. Retrieve Goal

Returns the goal with all nested questions ordered by `order` ascending.

- **Endpoint**: `GET /goals/{id}/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
{
  "id": 1,
  "dataset": 23,
  "problem_statement": "Why did Q3 revenue drop 18%?",
  "question_count": 2,
  "questions": [
    {
      "id": 1,
      "order": 0,
      "question": "Which region had the highest revenue decline?",
      "source": "manual",
      "created_at": "2026-05-01T09:05:00Z"
    },
    {
      "id": 2,
      "order": 1,
      "question": "Which product category had the most returns in Q3?",
      "source": "ai",
      "created_at": "2026-05-01T09:10:00Z"
    }
  ],
  "created_at": "2026-05-01T09:00:00Z",
  "updated_at": "2026-05-01T09:10:00Z"
}
```

---

### 4. Update Goal

Update the problem statement. Send only the fields to change.

- **Endpoint**: `PATCH /goals/{id}/`
- **Auth Required**: Yes
- **Request Body** *(any subset)*:
```json
{
  "problem_statement": "Revised: focusing on the North region only."
}
```
- **Response (200 OK)**: Updated `AnalysisGoal` object.

> `PUT` is not supported — use `PATCH` only.

---

### 5. Delete Goal

Permanently deletes the goal and all its questions. Any reports linked to this goal will have `goal` set to `null`.

- **Endpoint**: `DELETE /goals/{id}/`
- **Auth Required**: Yes
- **Response (204 No Content)**

---

### 6. AI Suggest Questions (Streaming SSE)

Calls the local Ollama model with the dataset's column headers and the goal's `problem_statement`. Streams back Q1, Q2, Q3... as Server-Sent Events. Questions are saved with `source: "ai"` when the stream completes.

- **Endpoint**: `POST /goals/{id}/suggest/`
- **Auth Required**: Yes
- **Response (200 OK)**:
  - `Content-Type: text/event-stream`
  - Streams SSE tokens until `[DONE]`:
  ```
  data: Q1: Which region had the highest revenue decline?\n\n
  data:  \n\n
  data: Q2: What is the month-over-month revenue trend?\n\n
  data: [DONE]\n\n
  ```
  - On error: `data: [ERROR] <message>\n\n`

> After `[DONE]` call `GET /goals/{id}/` to retrieve the saved AI questions.
> Requires the Ollama service running locally. Model is configured server-side.

---

### 7. Add Manual Question

Add a single manually-written question to a goal. Up to **20 questions** per goal.

- **Endpoint**: `POST /goals/{goal_id}/questions/`
- **Auth Required**: Yes
- **Request Body**:

| Field | Required | Description |
|---|---|---|
| `question` | Yes | The question text |
| `order` | No | Sort position (default `0`) |

```json
{
  "order": 0,
  "question": "Which region had the highest revenue decline?"
}
```

- **Response (201 Created)**: `AnalysisQuestion` object with `source: "manual"`.
- **Response (400)**: Goal already has 20 questions.

---

### 8. Update Question

Edit a question's text or order position.

- **Endpoint**: `PATCH /goals/{goal_id}/questions/{question_id}/`
- **Auth Required**: Yes
- **Request Body** *(any subset)*:
```json
{
  "question": "Which region had the steepest revenue drop in Q3?",
  "order": 2
}
```
- **Response (200 OK)**: Updated `AnalysisQuestion` object.

---

### 9. Delete Question

Remove a single question from the goal. The goal itself is not affected.

- **Endpoint**: `DELETE /goals/{goal_id}/questions/{question_id}/`
- **Auth Required**: Yes
- **Response (204 No Content)**

---

## 📝 Reports & Insights

The Reports module lets analysts **save chart snapshots with written insights** and **export the result as a PDF**. A report is a named document tied to a dataset. Each report contains ordered items — each item holds a chart image (PNG captured from ECharts), the chart params used to generate it, and a free-text annotation.

**Base path**: `/api/v1/reports/`

> Ownership is enforced on every endpoint — reports belonging to other users always return 404.

---

### Report Object

| Field | Type | Description |
|---|---|---|
| `id` | int | Unique identifier |
| `dataset` | int \| null | FK to the source dataset (nullable) |
| `goal` | int \| null | FK to the `AnalysisGoal` that motivated this report (nullable) |
| `title` | string | Report name |
| `description` | string | Optional summary text |
| `item_count` | int | Number of items in the report |
| `created_at` | datetime | Creation timestamp |
| `updated_at` | datetime | Last modification timestamp |
| `items` | array | Full item list — only present on `GET /reports/{id}/`, omitted on list |

### ReportItem Object

| Field | Type | Description |
|---|---|---|
| `id` | int | Unique identifier |
| `order` | int | Sort position (0-based, ascending) |
| `chart_type` | string | `bar` \| `line` \| `scatter` \| `histogram` \| `text` \| `""` |
| `chart_params` | object \| null | JSON snapshot of the query params used to generate the chart |
| `chart_image` | string | Base64-encoded PNG captured from ECharts (data URI prefix optional) |
| `annotation` | string | Analyst's written insight for this chart |
| `created_at` | datetime | When the item was added |

---

### 1. List Reports

Returns all reports owned by the authenticated user, ordered by most recently updated. Items are **not** included — use retrieve for that.

- **Endpoint**: `GET /reports/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
[
  {
    "id": 1,
    "dataset": 23,
    "title": "Q1 Sales Analysis",
    "description": "Drug sales breakdown by region.",
    "item_count": 4,
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T11:30:00Z"
  }
]
```

---

### 2. Create Report

- **Endpoint**: `POST /reports/`
- **Auth Required**: Yes
- **Request Body**:

| Field | Required | Description |
|---|---|---|
| `title` | Yes | Report name (max 255 chars) |
| `description` | No | Summary text |
| `dataset` | No | Dataset ID to associate with this report |
| `goal` | No | `AnalysisGoal` ID that motivated this report |

```json
{
  "title": "Q1 Sales Analysis",
  "description": "Drug sales breakdown by region.",
  "dataset": 23,
  "goal": 1
}
```

- **Response (201 Created)**: Full `Report` object including `items: []`.
- **Response (400)**: `title` is missing or blank.

---

### 3. Retrieve Report

Returns the full report with all items ordered by `order` ascending.

- **Endpoint**: `GET /reports/{id}/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
{
  "id": 1,
  "dataset": 23,
  "goal": 1,
  "title": "Q1 Sales Analysis",
  "description": "Drug sales breakdown by region.",
  "item_count": 2,
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-01T11:30:00Z",
  "items": [
    {
      "id": 1,
      "order": 0,
      "chart_type": "bar",
      "chart_params": { "x_col": "Drug_Name", "y_col": "Total_Price", "agg": "sum" },
      "chart_image": "<base64 PNG>",
      "annotation": "Aspirin dominates Q1 revenue at 42% of total sales.",
      "created_at": "2026-05-01T10:05:00Z"
    },
    {
      "id": 2,
      "order": 1,
      "chart_type": "line",
      "chart_params": { "x_col": "Date", "y_cols": ["Total_Price"] },
      "chart_image": "<base64 PNG>",
      "annotation": "Revenue dipped in week 3 — likely holiday effect.",
      "created_at": "2026-05-01T10:10:00Z"
    }
  ]
}
```

---

### 4. Update Report

Update `title` or `description`. Send only the fields you want to change.

- **Endpoint**: `PATCH /reports/{id}/`
- **Auth Required**: Yes
- **Request Body** *(any subset)*:
```json
{
  "title": "Q1 Sales Analysis — Final",
  "description": "Revised after peer review."
}
```
- **Response (200 OK)**: Updated `Report` object.

---

### 5. Delete Report

Permanently deletes the report and all its items.

- **Endpoint**: `DELETE /reports/{id}/`
- **Auth Required**: Yes
- **Response (204 No Content)**

---

### 6. Export Report as PDF

Generates and downloads a PDF containing the report title, description, and all items in order. Each item renders its chart image and annotation.

- **Endpoint**: `GET /reports/{id}/export/`
- **Auth Required**: Yes
- **Response (200 OK)**:
  - `Content-Type: application/pdf`
  - `Content-Disposition: attachment; filename="Q1_Sales_Analysis.pdf"`
  - Body: raw PDF bytes

> Items with no `chart_image` render a `[Chart image not available]` placeholder.
> Items with `chart_type: "text"` render annotation-only (no image slot).
> An empty report (no items) still produces a valid PDF with just the title and description.

---

### 7. Add Item to Report

Add a chart snapshot + annotation to a report. Up to **50 items** per report.

- **Endpoint**: `POST /reports/{id}/items/`
- **Auth Required**: Yes
- **Request Body**:

| Field | Required | Description |
|---|---|---|
| `order` | No | Sort position (default `0`) |
| `chart_type` | No | `bar` \| `line` \| `scatter` \| `histogram` \| `text` |
| `chart_params` | No | JSON object — the exact query params sent to the viz endpoint |
| `chart_image` | No | Base64 PNG string from `echarts.getDataURL()` |
| `annotation` | No | Analyst's written insight |

```json
{
  "order": 0,
  "chart_type": "bar",
  "chart_params": { "x_col": "Drug_Name", "y_col": "Total_Price", "agg": "sum", "limit": 10 },
  "chart_image": "<base64 PNG from echarts.getDataURL()>",
  "annotation": "Aspirin dominates Q1 revenue at 42% of total sales."
}
```

- **Response (201 Created)**: The new `ReportItem` object.
- **Response (400)**: Report already has 50 items.

> **Frontend flow:** call `chart.getDataURL('png')` on the ECharts instance → send the returned base64 string as `chart_image`.
> `chart_params` is a plain snapshot for reference — it is stored but not re-executed by the backend.

---

### 8. Update Item

Edit an item's annotation, order, or any other field. Send only the fields to change.

- **Endpoint**: `PATCH /reports/{id}/items/{item_id}/`
- **Auth Required**: Yes
- **Request Body** *(any subset)*:
```json
{
  "annotation": "Revised insight after data correction.",
  "order": 2
}
```
- **Response (200 OK)**: Updated `ReportItem` object.
- **Response (404)**: Item does not belong to this report, or report does not belong to the current user.

---

### 9. Delete Item

Remove a single item from the report. The report itself is not affected.

- **Endpoint**: `DELETE /reports/{id}/items/{item_id}/`
- **Auth Required**: Yes
- **Response (204 No Content)**

---

---

## 🤖 ML Studio

ML Studio provides a high-level interface for training machine learning models directly on your datasets. It supports regression, classification, and clustering tasks using Scikit-learn algorithms.

**Base path**: `/api/v1/mlstudio/`

### 1. List Models
Returns all models trained by the authenticated user.

- **Endpoint**: `GET /mlstudio/`
- **Auth Required**: Yes
- **Response (200 OK)**:
```json
[
  {
    "id": 1,
    "name": "Revenue Forecast",
    "task_type": "regression",
    "algorithm": "RandomForest",
    "status": "completed",
    "created_at": "2026-05-02T10:00:00Z"
  }
]
```

---

### 2. Train New Model
Initiates a model training job. Training is performed **asynchronously** in the background. The endpoint returns immediately with a `202 Accepted` status.

- **Endpoint**: `POST /mlstudio/`
- **Auth Required**: Yes
- **Request Body**:
```json
{
  "name": "Revenue Forecast",
  "dataset": 23,
  "task_type": "regression",
  "algorithm": "random_forest",
  "target_column": "Total_Price",
  "feature_columns": ["Drug_Name", "Quantity", "Region"],
  "hyperparameters": { "n_estimators": 100, "max_depth": 10 }
}
```

- **Response (202 Accepted)**: The initial model object with `status: "training"`. Use `GET /mlstudio/{id}/` to poll for completion.

---

### 3. Model Detail & Prediction
Retrieve detailed metrics or use the model to make predictions on new data.

- **Retrieve Detail**: `GET /mlstudio/{id}/`
- **Delete Model**: `DELETE /mlstudio/{id}/`
- **Run Prediction**: `POST /mlstudio/{id}/predict/`
  - **Real-time Prediction**: Pass raw data in the `data` field.
    - **Request Body**: `{ "data": [{ "Drug_Name": "Aspirin", "Quantity": 5, "Region": "North" }] }`
    - **Response**: `{ "predictions": [125.50] }`
  - **Batch Prediction**: Pass a `dataset_id` to predict on an entire dataset.
    - **Request Body**: `{ "dataset_id": 24 }`
    - **Response**: Full summary object containing a list of `{"row_index": idx, "prediction": val}`.

---

### 4. Discover Algorithms
Get a list of supported algorithms for a specific task type.

- **Endpoint**: `GET /mlstudio/algorithms/`
- **Query Params**: `?task_type=regression` (options: `regression`, `classification`, `clustering`)

---

## 💬 AI Chat on Data

Interact with your datasets using natural language. The AI Chat module uses local LLMs (Ollama) to answer questions based on the schema and data context.

**Base path**: `/api/v1/chat/`

### 1. Sessions & History
- **Create Session**: `POST /chat/` (Body: `{ "dataset": 23, "title": "Sales Discussion" }`)
- **List Sessions**: `GET /chat/`
- **Retrieve History**: `GET /chat/{id}/`
- **Clear History**: `DELETE /chat/{id}/clear/`

---

### 2. Chatting (Streaming Support)
- **Sync Message**: `POST /chat/{id}/message/` (Body: `{ "message": "What was the highest sale?" }`)
- **Stream Message (SSE)**: `POST /chat/{id}/stream/`
  - Streams tokens as they are generated.
  - Final reply is persisted to the database automatically.

---

## 📊 Dashboard Builder

Build custom interactive dashboards by arranging widgets in a 12-column grid layout.

**Base path**: `/api/v1/dashboards/`

### 1. Dashboard Management
- **Create Dashboard**: `POST /dashboards/` (Body: `{ "title": "Sales Performance", "description": "Weekly overview" }`)
- **Retrieve Dashboard**: `GET /dashboards/{id}/` (Returns full layout + widget data)
- **Refresh Dashboard**: `POST /dashboards/{id}/refresh/` (Re-calculates all widgets)

---

### 2. Widget Management
Widgets are attached to a dashboard and store their own chart parameters and grid coordinates.

- **Add Widget**: `POST /dashboards/{id}/widgets/`
  - **Request Body**:
  ```json
  {
    "title": "Monthly Revenue",
    "widget_type": "bar",
    "dataset": 23,
    "chart_params": { "x_col": "Month", "y_col": "Revenue", "agg": "sum" },
    "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4
  }
  ```
- **Update Layout/Params**: `PATCH /dashboards/{id}/widgets/{wid}/`
- **Refresh Single Widget**: `POST /dashboards/{id}/widgets/{wid}/refresh/`
- **Delete Widget**: `DELETE /dashboards/{id}/widgets/{wid}/`

---

### Standard Error Format
```json
{
  "detail": "Error message description"
}
```

### Common HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Validation error or missing fields |
| 401 | Unauthorized | Invalid or expired token |
| 403 | Forbidden | Permissions mapping error |
| 404 | Not Found | Resource not found |
| 500 | Internal Server Error | Dataset file could not be loaded, or an analysis computation failed |
---
