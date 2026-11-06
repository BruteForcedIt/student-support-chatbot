"""Staff accounts and login sessions (no extra libraries needed).

Two roles (see config.ROLES): "admin" = Hub staff, full access; "reviewer" = lecturer, Peer review only."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from . import config, db

ITERATIONS = 600_000          # slow on purpose: makes stolen password hashes hard to crack
MIN_PASSWORD = 10
_failed: dict[str, tuple[int, float]] = {}   # username -> (failed count, locked until)


def _forget_old_failures() -> None:
    """Keep the failed-sign-in table small (config.MAX_TRACKED_CLIENTS) so guesses at thousands of
    made-up usernames cannot fill the memory. Locks that are still running are never removed, so the
    lockout of a real account keeps working."""
    if len(_failed) <= config.MAX_TRACKED_CLIENTS:
        return
    now = time.time()
    for key in [k for k, (_, until) in _failed.items() if until and until <= now]:
        del _failed[key]                  # lock has run out: same as having no entry
    if len(_failed) > config.MAX_TRACKED_CLIENTS:
        unlocked = [k for k, (_, until) in _failed.items() if not until]
        for key in unlocked[:len(_failed) - config.MAX_TRACKED_CLIENTS]:   # oldest first (dicts keep order)
            del _failed[key]


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), ITERATIONS).hex()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(username: str, password: str, role: str = "admin") -> None:
    username = username.strip()
    if not 3 <= len(username) <= 50:
        raise ValueError("Username must be 3-50 characters.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    if role not in config.ROLES:
        raise ValueError(f"Role must be one of: {', '.join(config.ROLES)}.")
    salt = secrets.token_hex(16)
    with db.connect() as conn:
        # Sign-in ignores upper/lower case, so "Alice" and "alice" must not both exist.
        if conn.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (username,)).fetchone():
            raise ValueError("That username already exists.")
        conn.execute(
            "INSERT INTO users(username, password_hash, salt, created_at, role) VALUES (?,?,?,?,?)",
            (username, _hash(password, salt), salt, db.now_iso(), role),
        )


def login(username: str, password: str) -> dict:
    """Return {"token", "username", "role"}, or raise HTTPException."""
    key = username.strip().lower()
    count, locked_until = _failed.get(key, (0, 0.0))
    if locked_until > time.time():
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE lower(username)=?", (key,)).fetchone()
    # Always do the slow hash, even for unknown users, so timing doesn't reveal which usernames exist.
    expected = row["password_hash"] if row else "0" * 64
    candidate = _hash(password, row["salt"] if row else "00" * 16)
    if not row or not hmac.compare_digest(expected, candidate):
        count += 1
        locked = time.time() + config.LOCKOUT_MINUTES * 60 if count >= config.MAX_FAILED_LOGINS else 0.0
        _failed.pop(key, None)            # re-insert at the end, so the table stays oldest-first
        _failed[key] = (0 if locked else count, locked)
        _forget_old_failures()
        raise HTTPException(401, "Wrong username or password.")

    _failed.pop(key, None)
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=config.SESSION_HOURS)).isoformat(timespec="seconds")
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now_iso(),))
        conn.execute(
            "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?,?,?)",
            (_token_hash(token), row["id"], expires),
        )
    return {"token": token, "username": row["username"], "role": row["role"]}


def logout(token: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def change_password(username: str, current: str, new: str, keep_token: str) -> None:
    """Check the current password, save the new one, and sign out the account's other sessions."""
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row or not hmac.compare_digest(row["password_hash"], _hash(current, row["salt"])):
        raise HTTPException(400, "Your current password is not correct.")
    if len(new) < MIN_PASSWORD:
        raise HTTPException(400, f"The new password must be at least {MIN_PASSWORD} characters.")
    salt = secrets.token_hex(16)
    with db.connect() as conn:
        conn.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (_hash(new, salt), salt, row["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (row["id"], _token_hash(keep_token)))


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in.")
    return authorization[7:].strip()


def current_account(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: {"username", "role"} of the signed-in staff member, or 401."""
    token = _token_from_header(authorization)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT u.username, u.role, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash=?", (_token_hash(token),),
        ).fetchone()
    if not row or row["expires_at"] < db.now_iso():
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return {"username": row["username"], "role": row["role"]}


def current_user(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: the signed-in username (Hub staff or lecturer), or 401."""
    return current_account(authorization)["username"]


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: the signed-in username if it is a Hub staff (admin) account, otherwise 401/403."""
    account = current_account(authorization)
    if account["role"] != "admin":
        raise HTTPException(403, "Only Hub staff accounts can do this.")
    return account["username"]
