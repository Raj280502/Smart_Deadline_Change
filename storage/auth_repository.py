import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta

from cryptography.fernet import Fernet

from storage.database import get_connection


TOKEN_TTL_HOURS = 24 * 7


def create_user(email: str, password: str) -> dict:
    email = normalize_email(email)
    password_hash = hash_password(password)
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, password_hash, now),
    )
    conn.commit()
    user = get_user_by_id(cursor.lastrowid, conn)
    conn.close()
    return user


def authenticate_user(email: str, password: str) -> dict | None:
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return user


def get_user_by_email(email: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
        (normalize_email(email),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int, conn=None) -> dict | None:
    owns_conn = conn is None
    conn = conn or get_connection()
    row = conn.execute(
        "SELECT id, email, password_hash, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if owns_conn:
        conn.close()
    return dict(row) if row else None


def save_user_credentials(user_id: int, credentials: dict):
    encrypted = encrypt_json(credentials)
    now = datetime.now().isoformat()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO user_credentials (user_id, encrypted_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            encrypted_json = excluded.encrypted_json,
            updated_at = excluded.updated_at
        """,
        (user_id, encrypted, now),
    )
    conn.commit()
    conn.close()


def get_user_credentials(user_id: int) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT encrypted_json FROM user_credentials WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {}
    return decrypt_json(row["encrypted_json"])


def get_credential_status(user_id: int) -> dict:
    creds = get_user_credentials(user_id)
    return {
        "groq_api_key": bool(creds.get("groq_api_key")),
        "telegram_bot_token": bool(creds.get("telegram_bot_token")),
        "telegram_chat_id": bool(creds.get("telegram_chat_id")),
        "tpo_username": bool(creds.get("tpo_username")),
        "tpo_password": bool(creds.get("tpo_password")),
        "tpo_login_url": bool(creds.get("tpo_login_url")),
        "tpo_drives_url": bool(creds.get("tpo_drives_url")),
    }


def create_access_token(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "exp": (datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)).timestamp(),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = sign(body)
    return f"{body}.{signature}"


def verify_access_token(token: str) -> dict | None:
    try:
        body, signature = token.split(".", 1)
        if not hmac.compare_digest(sign(body), signature):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body.encode()).decode())
        if datetime.utcnow().timestamp() > payload["exp"]:
            return None
        return get_user_by_id(int(payload["sub"]))
    except Exception:
        return None


def public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"]}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        120000,
    ).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _, salt, expected = stored_hash.split("$", 2)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            120000,
        ).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def encrypt_json(value: dict) -> str:
    return get_fernet().encrypt(json.dumps(value).encode()).decode()


def decrypt_json(value: str) -> dict:
    return json.loads(get_fernet().decrypt(value.encode()).decode())


def get_fernet() -> Fernet:
    secret = os.getenv("AUTH_SECRET", "dev-change-this-auth-secret")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def sign(value: str) -> str:
    secret = os.getenv("AUTH_SECRET", "dev-change-this-auth-secret")
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()
