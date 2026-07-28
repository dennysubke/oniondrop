from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from pathlib import Path
from typing import Any


SUPPORTED_LANGUAGES = ("en", "de", "es", "it", "fr", "zh", "ja", "ru")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


def generate_password_hash(password: str) -> str:
    """Create a portable scrypt password hash using only the standard library."""
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("password_too_long")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(derived).decode("ascii").rstrip("="),
    )


def check_password_hash(encoded: str, password: str) -> bool:
    if len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        algorithm, n_value, r_value, p_value, salt_text, digest_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        n, r, p = int(n_value), int(r_value), int(p_value)
        if n != 2**14 or r != 8 or p != 1:
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class SettingsManager:
    """Persistent platform-neutral application and authentication settings."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._initial_settings())
        else:
            self._migrate()

    def _initial_settings(self) -> dict[str, Any]:
        mode = os.environ.get("ONIONDROP_AUTH_MODE", "setup").strip().lower()
        language = self._language(os.environ.get("ONIONDROP_DEFAULT_LANGUAGE", "en"))
        username = os.environ.get("ONIONDROP_ADMIN_USERNAME", "admin").strip() or "admin"
        if not USERNAME_RE.fullmatch(username):
            username = "admin"
        password = os.environ.get("ONIONDROP_ADMIN_PASSWORD", "")
        configured = False
        auth_enabled = False
        password_hash = None

        if mode == "disabled":
            configured = True
        elif mode == "enabled" and MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            configured = True
            auth_enabled = True
            password_hash = generate_password_hash(password)

        return {
            "version": 1,
            "configured": configured,
            "auth_enabled": auth_enabled,
            "username": username,
            "password_hash": password_hash,
            "default_language": language,
            "session_secret": os.environ.get("ONIONDROP_SECRET_KEY") or secrets.token_urlsafe(48),
        }

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (OSError, json.JSONDecodeError, ValueError):
            return self._initial_settings()

    def _write(self, data: dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix="settings-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _migrate(self) -> None:
        with self.lock:
            data = self._read()
            changed = False
            defaults = self._initial_settings()
            for key, value in defaults.items():
                if key not in data:
                    data[key] = value
                    changed = True
            if data.get("default_language") not in SUPPORTED_LANGUAGES:
                data["default_language"] = "en"
                changed = True
            if changed:
                self._write(data)

    @staticmethod
    def _language(value: str | None) -> str:
        language = (value or "en").lower().split("-")[0]
        return language if language in SUPPORTED_LANGUAGES else "en"

    @property
    def secret_key(self) -> str:
        return str(self._read().get("session_secret") or secrets.token_urlsafe(48))

    def public(self) -> dict[str, Any]:
        data = self._read()
        return {
            "configured": bool(data.get("configured")),
            "auth_enabled": bool(data.get("auth_enabled")),
            "username": str(data.get("username") or "admin"),
            "default_language": self._language(data.get("default_language")),
        }

    def verify(self, username: str, password: str) -> bool:
        data = self._read()
        expected = str(data.get("username") or "admin")
        password_hash = data.get("password_hash")
        return bool(
            data.get("auth_enabled")
            and username == expected
            and isinstance(password_hash, str)
            and check_password_hash(password_hash, password)
        )

    def configure(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            data = self._read()
            if data.get("configured"):
                raise ValueError("already_configured")
            auth_enabled = bool(payload.get("auth_enabled"))
            username = str(payload.get("username") or "admin").strip()
            password = str(payload.get("password") or "")
            if not USERNAME_RE.fullmatch(username):
                raise ValueError("invalid_username")
            if auth_enabled and len(password) < MIN_PASSWORD_LENGTH:
                raise ValueError("password_too_short")
            if len(password) > MAX_PASSWORD_LENGTH:
                raise ValueError("password_too_long")
            data.update(
                configured=True,
                auth_enabled=auth_enabled,
                username=username,
                password_hash=generate_password_hash(password) if auth_enabled else None,
                default_language=self._language(payload.get("default_language")),
            )
            self._write(data)
            return self.public()

    def update(self, payload: dict[str, Any], current_password: str = "") -> dict[str, Any]:
        with self.lock:
            data = self._read()
            currently_enabled = bool(data.get("auth_enabled"))
            requested_enabled = bool(payload.get("auth_enabled", currently_enabled))
            username = str(payload.get("username") or data.get("username") or "admin").strip()
            new_password = str(payload.get("new_password") or "")
            language = self._language(payload.get("default_language") or data.get("default_language"))

            if not USERNAME_RE.fullmatch(username):
                raise ValueError("invalid_username")
            sensitive_change = requested_enabled != currently_enabled or username != data.get("username") or bool(new_password)
            if currently_enabled and sensitive_change:
                password_hash = data.get("password_hash")
                if not isinstance(password_hash, str) or not check_password_hash(password_hash, current_password):
                    raise ValueError("current_password_invalid")
            if requested_enabled and not currently_enabled and len(new_password) < MIN_PASSWORD_LENGTH:
                raise ValueError("password_too_short")
            if new_password and len(new_password) < MIN_PASSWORD_LENGTH:
                raise ValueError("password_too_short")
            if len(new_password) > MAX_PASSWORD_LENGTH:
                raise ValueError("password_too_long")

            data["auth_enabled"] = requested_enabled
            data["username"] = username
            data["default_language"] = language
            if new_password:
                data["password_hash"] = generate_password_hash(new_password)
            elif not requested_enabled:
                data["password_hash"] = None
            self._write(data)
            return self.public()
