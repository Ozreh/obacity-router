import hashlib
import hmac
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

import userdb

BASE_DIR = Path(__file__).resolve().parent
SECRET_FILE = BASE_DIR / ".auth_secret"
GOOGLE_ID_FILE = BASE_DIR / "google_client_id.txt"
TOKEN_TTL_SECONDS = 7 * 24 * 3600
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128
NAME_MAX_LEN = 60
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW_S = 300
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def load_google_client_id() -> str:
    value = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not value and GOOGLE_ID_FILE.exists():
        value = GOOGLE_ID_FILE.read_text(encoding="utf-8").strip()
    return value


def load_jwt_secret() -> str:
    value = os.environ.get("AUTH_SECRET", "").strip()
    if value:
        return value
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    value = secrets.token_hex(32)
    SECRET_FILE.write_text(value, encoding="utf-8")
    return value


GOOGLE_CLIENT_ID = load_google_client_id()
JWT_SECRET = load_jwt_secret()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


DUMMY_HASH = hash_password("dummy-password-for-timing")

login_failures: dict = {}


def rate_limit_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}|{email}"


def check_rate_limit(key: str):
    now = time.time()
    recent = [t for t in login_failures.get(key, []) if now - t < LOGIN_WINDOW_S]
    if recent:
        login_failures[key] = recent
    else:
        login_failures.pop(key, None)
    if len(recent) >= LOGIN_MAX_FAILS:
        raise HTTPException(429, "Слишком много попыток входа. Подождите несколько минут")


def register_failure(key: str):
    login_failures.setdefault(key, []).append(time.time())


def issue_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def public_user(row) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def auth_response(row) -> dict:
    return {"token": issue_token(row["id"]), "user": public_user(row)}


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise HTTPException(400, "Введите корректный email")
    return email


def clean_name(value: str, email: str) -> str:
    name = (value or "").strip()[:NAME_MAX_LEN]
    return name or email.split("@")[0]


bearer = HTTPBearer(auto_error=False)


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(401, "Требуется вход")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Сессия истекла, войдите снова")
    row = userdb.user_by_id(user_id)
    if row is None:
        raise HTTPException(401, "Сессия истекла, войдите снова")
    return public_user(row)


def verify_google_token(credential: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(credential, google_requests.Request(), GOOGLE_CLIENT_ID)


class RegisterBody(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


class GoogleBody(BaseModel):
    credential: str


@asynccontextmanager
async def lifespan(_app):
    userdb.init_db()
    yield


router = APIRouter(prefix="/auth")


@router.get("/config")
def auth_config():
    return {"google_client_id": GOOGLE_CLIENT_ID or None}


@router.post("/register")
def register(body: RegisterBody):
    email = normalize_email(body.email)
    if not (PASSWORD_MIN_LEN <= len(body.password) <= PASSWORD_MAX_LEN):
        raise HTTPException(400, f"Пароль должен быть от {PASSWORD_MIN_LEN} до {PASSWORD_MAX_LEN} символов")
    name = clean_name(body.name, email)
    password_hash = hash_password(body.password)
    try:
        row = userdb.create_user(email, name, password_hash=password_hash)
    except userdb.IntegrityError:
        raise HTTPException(409, "Этот email уже зарегистрирован")
    return auth_response(row)


@router.post("/login")
def login(body: LoginBody, request: Request):
    email = (body.email or "").strip().lower()
    key = rate_limit_key(request, email)
    check_rate_limit(key)
    row = userdb.user_for_login(email)
    has_password = row is not None and row["password_hash"] is not None
    stored = row["password_hash"] if has_password else DUMMY_HASH
    password_ok = verify_password(body.password[:PASSWORD_MAX_LEN], stored)
    if not (has_password and password_ok):
        register_failure(key)
        raise HTTPException(401, "Неверный email или пароль")
    login_failures.pop(key, None)
    return auth_response(row)


@router.post("/google")
def google_login(body: GoogleBody):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Вход через Google не настроен")
    try:
        info = verify_google_token(body.credential)
    except Exception:
        raise HTTPException(401, "Не удалось подтвердить вход через Google")
    email = (info.get("email") or "").strip().lower()
    sub = info.get("sub")
    if not email or not sub or not info.get("email_verified"):
        raise HTTPException(401, "Google не подтвердил email")
    row = userdb.google_user(email, sub, clean_name(info.get("name", ""), email))
    return auth_response(row)


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
