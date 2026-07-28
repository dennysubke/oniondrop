from __future__ import annotations

import io
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from flask import Flask, jsonify, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .manager import OnionDropManager
from .preview import direct_preview_kind, guessed_mime
from .settings import SUPPORTED_LANGUAGES, SettingsManager

APP_VERSION = "0.2.0"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def json_error(code: str, status: int = 400, detail: str | None = None):
    payload: dict[str, Any] = {"ok": False, "error": code, "code": code}
    if detail:
        payload["detail"] = detail
    return jsonify(payload), status


class LoginLimiter:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            queue = self.attempts[key]
            while queue and now - queue[0] > 300:
                queue.popleft()
            return len(queue) < 5

    def fail(self, key: str) -> None:
        with self.lock:
            self.attempts[key].append(time.monotonic())

    def clear(self, key: str) -> None:
        with self.lock:
            self.attempts.pop(key, None)


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        MAX_CONTENT_LENGTH=2_000_000,
        JSON_SORT_KEYS=False,
        SEND_FILE_MAX_AGE_DEFAULT=0,
        SESSION_COOKIE_NAME="oniondrop_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("ONIONDROP_HTTPS", "false").lower() in {"1", "true", "yes"},
        PERMANENT_SESSION_LIFETIME=timedelta(hours=env_int("ONIONDROP_SESSION_HOURS", 12, 1, 720)),
    )
    if config:
        app.config.update(config)

    data_root = Path(app.config.get("DATA_ROOT") or os.environ.get("ONIONDROP_DATA_DIR", "/data"))
    mock = bool(app.config.get("MOCK", os.environ.get("ONIONDROP_MOCK", "").lower() in {"1", "true", "yes"}))
    settings = SettingsManager(data_root / "settings.json")
    manager = OnionDropManager(data_root, mock=mock)
    limiter = LoginLimiter()
    app.secret_key = settings.secret_key
    app.extensions["oniondrop_manager"] = manager
    app.extensions["oniondrop_settings"] = settings

    if os.environ.get("ONIONDROP_TRUST_PROXY", "false").lower() in {"1", "true", "yes"}:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)  # type: ignore[method-assign]

    def csrf_token() -> str:
        token = session.get("csrf_token")
        if not isinstance(token, str):
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def authenticated() -> bool:
        public = settings.public()
        return not public["auth_enabled"] or bool(session.get("authenticated"))

    @app.before_request
    def access_control():
        csrf_token()
        endpoint = request.endpoint or ""
        if endpoint in {"static", "index", "health", "bootstrap"}:
            return None
        if request.method in UNSAFE_METHODS:
            supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not supplied or not secrets.compare_digest(str(supplied), csrf_token()):
                return json_error("csrf_invalid", 403)
        if endpoint in {"setup", "login"}:
            return None
        current = settings.public()
        if not current["configured"]:
            return json_error("setup_required", 428)
        if current["auth_enabled"] and not session.get("authenticated"):
            return json_error("authentication_required", 401)
        return None

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
        )
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(413)
    def too_large(_error):
        return json_error("request_too_large", 413)

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            version=APP_VERSION,
            onionshare_version=os.environ.get("ONIONSHARE_VERSION", "2.6.4"),
            mock=mock,
        )

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "version": APP_VERSION, "mock": mock})

    @app.get("/api/bootstrap")
    def bootstrap():
        current = settings.public()
        return jsonify(
            {
                "ok": True,
                **current,
                "authenticated": authenticated(),
                "csrf_token": csrf_token(),
                "version": APP_VERSION,
                "onionshare_version": os.environ.get("ONIONSHARE_VERSION", "2.6.4"),
                "supported_languages": list(SUPPORTED_LANGUAGES),
                "mock": mock,
            }
        )

    @app.post("/api/setup")
    def setup():
        payload = request.get_json(silent=True) or {}
        try:
            current = settings.configure(payload)
        except ValueError as exc:
            return json_error(str(exc), 409 if str(exc) == "already_configured" else 400)
        session.clear()
        session["csrf_token"] = secrets.token_urlsafe(32)
        if current["auth_enabled"]:
            session["authenticated"] = True
            session["username"] = current["username"]
            session.permanent = True
        return jsonify({"ok": True, "settings": current, "csrf_token": session["csrf_token"]})

    @app.post("/api/login")
    def login():
        current = settings.public()
        if not current["configured"]:
            return json_error("setup_required", 428)
        if not current["auth_enabled"]:
            return jsonify({"ok": True, "auth_enabled": False})
        key = request.remote_addr or "unknown"
        if not limiter.allowed(key):
            return json_error("too_many_login_attempts", 429)
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username") or "")
        password = str(payload.get("password") or "")
        if not settings.verify(username, password):
            limiter.fail(key)
            time.sleep(0.35)
            return json_error("invalid_credentials", 401)
        limiter.clear(key)
        session.clear()
        session["csrf_token"] = secrets.token_urlsafe(32)
        session["authenticated"] = True
        session["username"] = username
        session.permanent = True
        return jsonify({"ok": True, "csrf_token": session["csrf_token"]})

    @app.post("/api/logout")
    def logout():
        session.clear()
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify({"ok": True, "csrf_token": session["csrf_token"]})

    @app.get("/api/settings")
    def get_settings():
        return jsonify({"ok": True, "settings": settings.public()})

    @app.patch("/api/settings")
    def update_settings():
        payload = request.get_json(silent=True) or {}
        previous = settings.public()
        try:
            updated = settings.update(payload, current_password=str(payload.get("current_password") or ""))
        except ValueError as exc:
            return json_error(str(exc), 400)
        if updated["auth_enabled"]:
            # Enabling protection from an unprotected session must not immediately lock out
            # the administrator who just configured it.
            if not previous["auth_enabled"]:
                session["authenticated"] = True
                session["username"] = updated["username"]
                session.permanent = True
        else:
            session.pop("authenticated", None)
            session.pop("username", None)
        return jsonify({"ok": True, "settings": updated})

    @app.get("/api/tor/status")
    def tor_status():
        return jsonify({"ok": True, "tor": manager.tor_status()})

    @app.get("/api/inboxes")
    def list_inboxes():
        return jsonify({"ok": True, "inboxes": manager.list()})

    @app.post("/api/inboxes")
    def create_inbox():
        try:
            inbox = manager.create(request.get_json(silent=True) or {})
            return jsonify({"ok": True, "inbox": inbox}), 201
        except (ValueError, TypeError) as exc:
            return json_error(str(exc))

    @app.get("/api/inboxes/<inbox_id>")
    def get_inbox(inbox_id: str):
        inbox = manager.get(inbox_id)
        return jsonify({"ok": True, "inbox": inbox}) if inbox else json_error("inbox_not_found", 404)

    @app.patch("/api/inboxes/<inbox_id>")
    def update_inbox(inbox_id: str):
        try:
            return jsonify({"ok": True, "inbox": manager.update(inbox_id, request.get_json(silent=True) or {})})
        except KeyError:
            return json_error("inbox_not_found", 404)
        except (ValueError, TypeError) as exc:
            return json_error(str(exc))

    @app.post("/api/inboxes/<inbox_id>/start")
    def start_inbox(inbox_id: str):
        try:
            return jsonify({"ok": True, "inbox": manager.start(inbox_id)})
        except KeyError:
            return json_error("inbox_not_found", 404)
        except ValueError as exc:
            return json_error(str(exc), 409)
        except OSError as exc:
            return json_error("onionshare_start_failed", 500, str(exc))

    @app.post("/api/inboxes/<inbox_id>/stop")
    def stop_inbox(inbox_id: str):
        if not manager.get(inbox_id):
            return json_error("inbox_not_found", 404)
        return jsonify({"ok": True, "inbox": manager.stop(inbox_id)})

    @app.delete("/api/inboxes/<inbox_id>")
    def delete_inbox(inbox_id: str):
        keep_files = request.args.get("keep_files", "false").lower() == "true"
        if not manager.delete(inbox_id, delete_files=not keep_files):
            return json_error("inbox_not_found", 404)
        return jsonify({"ok": True})

    @app.get("/api/inboxes/<inbox_id>/files")
    def list_files(inbox_id: str):
        if not manager.get(inbox_id):
            return json_error("inbox_not_found", 404)
        return jsonify({"ok": True, "files": manager.list_files(inbox_id)})

    @app.get("/api/inboxes/<inbox_id>/files/download")
    def download_file(inbox_id: str):
        relative_path = request.args.get("path", "")
        try:
            path = manager.safe_file(inbox_id, relative_path)
            return send_file(path, as_attachment=True, download_name=path.name, max_age=0)
        except (ValueError, FileNotFoundError):
            return json_error("file_not_found", 404)

    @app.get("/api/inboxes/<inbox_id>/files/inline")
    def inline_file(inbox_id: str):
        relative_path = request.args.get("path", "")
        try:
            path = manager.safe_file(inbox_id, relative_path)
        except (ValueError, FileNotFoundError):
            return json_error("file_not_found", 404)
        if not direct_preview_kind(path):
            return json_error("preview_not_supported", 415)
        response = send_file(path, mimetype=guessed_mime(path), as_attachment=False, conditional=True, max_age=0)
        response.headers["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(path.name)}"
        return response

    @app.get("/api/inboxes/<inbox_id>/files/preview")
    def preview_file(inbox_id: str):
        relative_path = request.args.get("path", "")
        try:
            inline_url = url_for("inline_file", inbox_id=inbox_id, path=relative_path)
            return jsonify({"ok": True, "preview": manager.preview(inbox_id, relative_path, inline_url)})
        except (ValueError, FileNotFoundError):
            return json_error("file_not_found", 404)

    @app.get("/api/inboxes/<inbox_id>/files/sha256")
    def file_checksum(inbox_id: str):
        relative_path = request.args.get("path", "")
        try:
            return jsonify({"ok": True, "sha256": manager.checksum_file(inbox_id, relative_path)})
        except (ValueError, FileNotFoundError):
            return json_error("file_not_found", 404)

    @app.post("/api/inboxes/<inbox_id>/files/zip")
    def zip_files(inbox_id: str):
        payload = request.get_json(silent=True) or {}
        paths = payload.get("paths")
        if not isinstance(paths, list):
            return json_error("no_files_selected")
        try:
            output = manager.create_zip(inbox_id, [str(item) for item in paths])
        except KeyError:
            return json_error("inbox_not_found", 404)
        except (ValueError, FileNotFoundError) as exc:
            return json_error(str(exc), 400)
        response = send_file(
            output,
            as_attachment=True,
            download_name=f"oniondrop-{inbox_id}-{time.strftime('%Y%m%d-%H%M%S')}.zip",
            mimetype="application/zip",
            max_age=0,
        )
        response.call_on_close(lambda: output.unlink(missing_ok=True))
        return response

    @app.delete("/api/inboxes/<inbox_id>/files")
    def delete_file(inbox_id: str):
        relative_path = request.args.get("path", "")
        try:
            manager.delete_file(inbox_id, relative_path)
            return jsonify({"ok": True})
        except (ValueError, FileNotFoundError):
            return json_error("file_not_found", 404)

    @app.get("/api/inboxes/<inbox_id>/logs")
    def logs(inbox_id: str):
        if not manager.get(inbox_id):
            return json_error("inbox_not_found", 404)
        return jsonify({"ok": True, "logs": manager.log_tail(inbox_id)})

    @app.get("/api/inboxes/<inbox_id>/export")
    def export_config(inbox_id: str):
        try:
            path = manager.export_path(inbox_id)
            return send_file(path, as_attachment=True, download_name=f"oniondrop-{inbox_id}.json", mimetype="application/json", max_age=0)
        except KeyError:
            return json_error("inbox_not_found", 404)
        except ValueError as exc:
            return json_error(str(exc), 409)

    @app.post("/api/import")
    def import_config():
        uploaded = request.files.get("config")
        if not uploaded:
            return json_error("no_config_selected")
        try:
            inbox = manager.import_config(
                uploaded.read(),
                name=request.form.get("name") or None,
                autostart=request.form.get("autostart", "true").lower() == "true",
            )
            return jsonify({"ok": True, "inbox": inbox}), 201
        except ValueError as exc:
            return json_error(str(exc))

    @app.get("/api/inboxes/<inbox_id>/qr")
    def qr_code(inbox_id: str):
        inbox = manager.get(inbox_id)
        if not inbox:
            return json_error("inbox_not_found", 404)
        kind = request.args.get("kind", "url")
        value = inbox.get("private_key") if kind == "key" else inbox.get("url")
        if not value:
            return json_error("value_not_ready", 409)
        image_format = request.args.get("format", "svg").lower()
        download = request.args.get("download", "false").lower() == "true"
        output = io.BytesIO()
        if image_format == "png":
            image = qrcode.make(value, box_size=10, border=3)
            image.save(output, format="PNG")
            mimetype = "image/png"
            extension = "png"
        else:
            image = qrcode.make(value, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
            image.save(output)
            mimetype = "image/svg+xml"
            extension = "svg"
        output.seek(0)
        name = f"oniondrop-{inbox_id}-{kind}.{extension}"
        return send_file(output, mimetype=mimetype, as_attachment=download, download_name=name, max_age=0)

    return app
