from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import secrets
import time
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status

from app.config import get_settings

SESSION_COOKIE_NAME = "habitflow_session"
PBKDF2_ITERATIONS = 260_000

# In-memory brute-force protection for login attempts: {ip: [timestamps]}
_FAILED_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
MAX_FAILED_ATTEMPTS = 7
LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Create a PBKDF2-HMAC-SHA256 password hash string."""
    salt_val = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_val.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    digest_b64 = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_val}${digest_b64}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt_val = parts[2]
        expected_b64 = parts[3]

        dk = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt_val.encode("utf-8"),
            iterations,
        )
        actual_b64 = base64.urlsafe_b64encode(dk).decode("ascii").rstrip("=")
        return hmac.compare_digest(actual_b64, expected_b64)
    except Exception:
        return False


def verify_owner_credentials(username: str, password: str) -> bool:
    """Verify single-owner login credentials against environment settings."""
    settings = get_settings()
    username_ok = hmac.compare_digest(
        username.strip().encode("utf-8"),
        settings.owner_username.strip().encode("utf-8"),
    )
    if not username_ok:
        # Run a dummy PBKDF2 calculation to prevent timing attacks
        hash_password(password, salt="0000000000000000")
        return False

    if settings.owner_password_hash:
        return verify_password(password, settings.owner_password_hash.strip())

    if settings.owner_password:
        return hmac.compare_digest(
            password.encode("utf-8"),
            settings.owner_password.encode("utf-8"),
        )

    return False


def _sign_payload(payload_b64: str, secret_key: str) -> str:
    sig = hmac.new(
        secret_key.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def create_session_token(
    username: str,
    max_age_seconds: Optional[int] = None,
    csrf_token: Optional[str] = None,
) -> str:
    """Create an HMAC-SHA256 signed session token containing owner sub, exp, and csrf token."""
    settings = get_settings()
    ttl = max_age_seconds or settings.session_max_age_seconds
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + ttl,
        "csrf": csrf_token or secrets.token_urlsafe(24),
    }
    raw_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
    signature_b64 = _sign_payload(payload_b64, settings.secret_key)
    return f"{payload_b64}.{signature_b64}"


def verify_session_token(token: str) -> Optional[dict]:
    """Verify signature and expiration of a session token; return payload dict or None."""
    if not token or "." not in token:
        return None
    settings = get_settings()
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = _sign_payload(payload_b64, settings.secret_key)
        if not hmac.compare_digest(sig_b64, expected_sig):
            return None

        padding = "=" * (-len(payload_b64) % 4)
        raw_json = base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8")
        data = json.loads(raw_json)
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        if not hmac.compare_digest(str(data.get("sub", "")), settings.owner_username):
            return None
        return data
    except Exception:
        return None


def check_rate_limit(client_ip: str) -> None:
    """Raise 429 Too Many Requests if client_ip has exceeded failed login attempts."""
    now = time.time()
    attempts = [
        ts for ts in _FAILED_LOGIN_ATTEMPTS.get(client_ip, [])
        if now - ts < LOCKOUT_WINDOW_SECONDS
    ]
    _FAILED_LOGIN_ATTEMPTS[client_ip] = attempts
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много неудачных попыток входа. Подождите 5 минут.",
        )


def record_failed_login(client_ip: str) -> None:
    now = time.time()
    attempts = _FAILED_LOGIN_ATTEMPTS.setdefault(client_ip, [])
    attempts.append(now)


def clear_failed_logins(client_ip: str) -> None:
    _FAILED_LOGIN_ATTEMPTS.pop(client_ip, None)


def get_session_from_request(request: Request) -> Optional[dict]:
    """Extract and validate the owner session from request cookies."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return verify_session_token(token)


def require_owner_api(request: Request) -> dict:
    """FastAPI dependency protecting all private API endpoints.

    - Requires a valid signed session cookie.
    - Enforces CSRF protection on state-changing HTTP methods (POST, PUT, PATCH, DELETE).
    """
    session = get_session_from_request(request)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход владельца приложения",
        )

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        header_csrf = request.headers.get("X-CSRF-Token")
        expected_csrf = session.get("csrf", "")
        if not header_csrf or not hmac.compare_digest(header_csrf, expected_csrf):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недействительный или отсутствующий CSRF-токен",
            )

    return session


def main() -> None:
    """CLI utility to generate SECRET_KEY and OWNER_PASSWORD_HASH for .env."""
    parser = argparse.ArgumentParser(description="HabitFlow Owner Security CLI")
    parser.add_argument(
        "--hash-password",
        dest="password",
         nargs="?",
        const="__PROMPT__",
        help="Сгенерировать PBKDF2-хеш пароля владельца для OWNER_PASSWORD_HASH",
    )
    parser.add_argument(
        "--generate-secret",
        action="store_true",
        help="Сгенерировать криптостойкий SECRET_KEY",
    )
    args = parser.parse_args()

    if args.generate_secret:
        print(f"SECRET_KEY=\"{secrets.token_urlsafe(48)}\"")

    if args.password is not None:
        pwd = getpass.getpass("Введите пароль владельца: ") if args.password == "__PROMPT__" else args.password
        if len(pwd) < 6:
            raise SystemExit("Ошибка: пароль должен содержать минимум 6 символов.")
        print(f"OWNER_PASSWORD_HASH='{hash_password(pwd)}'")

    if not args.generate_secret and args.password is None:
        parser.print_help()


if __name__ == "__main__":
    main()
