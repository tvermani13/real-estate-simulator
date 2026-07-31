from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Cookie, Depends, Header, HTTPException, Response, status

from app.core.config import settings
from app.core.database import connection


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user(name: str, email: str, password: str) -> dict[str, str]:
    user_id = str(uuid4())
    created_at = isoformat(utc_now())
    try:
        with connection() as db:
            db.execute(
                "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, name.strip(), email.strip().lower(), hash_password(password), created_at),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="An account with that email already exists",
        ) from exc
    return {"id": user_id, "name": name.strip(), "email": email.strip().lower(), "created_at": created_at}


def authenticate_user(email: str, password: str) -> dict[str, str] | None:
    with connection() as db:
        row = db.execute(
            "SELECT id, name, email, password_hash, created_at FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip(),),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return {key: row[key] for key in ("id", "name", "email", "created_at")}


def create_session(user_id: str, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    now = utc_now()
    expires_at = now + timedelta(days=settings.session_days)
    with connection() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (isoformat(now),))
        db.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, isoformat(expires_at), isoformat(now)),
        )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_days * 24 * 60 * 60,
        expires=expires_at,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def revoke_session(token: str | None, response: Response) -> None:
    if token:
        with connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_user(
    authorization: Annotated[str | None, Header()] = None,
    session_cookie: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> dict[str, str]:
    token = _bearer_token(authorization) or session_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    with connection() as db:
        row = db.execute(
            """
            SELECT users.id, users.name, users.email, users.created_at, sessions.expires_at
            FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
            """,
            (_token_hash(token),),
        ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) <= utc_now():
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return {key: row[key] for key in ("id", "name", "email", "created_at")}


CurrentUser = Annotated[dict[str, str], Depends(current_user)]
