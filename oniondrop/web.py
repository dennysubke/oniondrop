from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import qrcode
import qrcode.image.svg
from flask import Flask, jsonify, render_template, request, send_file

from .manager import OnionDropManager


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        MAX_CONTENT_LENGTH=1_000_000,
        JSON_SORT_KEYS=False,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    if config:
        app.config.update(config)
    data_root = Path(app.config.get("DATA_ROOT") or os.environ.get("ONIONDROP_DATA_DIR", "/data"))
    mock = bool(app.config.get("MOCK", os.environ.get("ONIONDROP_MOCK", "").lower() in {"1", "true", "yes"}))
    manager = OnionDropManager(data_root, mock=mock)
    app.extensions["oniondrop_manager"] = manager

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'self'"
        )
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            version="0.1.0",
            onionshare_version=os.environ.get("ONIONSHARE_VERSION", "2.6.4"),
            mock=mock,
        )

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "version": "0.1.0", "mock": mock})

    @app.get("/api/inboxes")
    def list_inboxes():
        return jsonify({"ok": True, "inboxes": manager.list()})

    @app.post("/api/inboxes")
    def create_inbox():
        payload = request.get_json(silent=True) or {}
        try:
            inbox = manager.create(payload)
            return jsonify({"ok": True, "inbox": inbox}), 201
        except (ValueError, TypeError) as exc:
            return json_error(str(exc))

    @app.get("/api/inboxes/<inbox_id>")
    def get_inbox(inbox_id: str):
        inbox = manager.get(inbox_id)
        return jsonify({"ok": True, "inbox": inbox}) if inbox else json_error("Inbox not found", 404)

    @app.patch("/api/inboxes/<inbox_id>")
    def update_inbox(inbox_id: str):
        try:
            inbox = manager.update(inbox_id, request.get_json(silent=True) or {})
            return jsonify({"ok": True, "inbox": inbox})
        except KeyError:
            return json_error("Inbox not found", 404)
        except (ValueError, TypeError) as exc:
            return json_error(str(exc))

    @app.post("/api/inboxes/<inbox_id>/start")
    def start_inbox(inbox_id: str):
        try:
            return jsonify({"ok": True, "inbox": manager.start(inbox_id)})
        except KeyError:
            return json_error("Inbox not found", 404)
        except ValueError as exc:
            return json_error(str(exc), 409)
        except OSError as exc:
            return json_error(f"Unable to start OnionShare: {exc}", 500)

    @app.post("/api/inboxes/<inbox_id>/stop")
    def stop_inbox(inbox_id: str):
        if not manager.get(inbox_id):
            return json_error("Inbox not found", 404)
        return jsonify({"ok": True, "inbox": manager.stop(inbox_id)})

    @app.delete("/api/inboxes/<inbox_id>")
    def delete_inbox(inbox_id: str):
        keep_files = request.args.get("keep_files", "false").lower() == "true"
        if not manager.delete(inbox_id, delete_files=not keep_files):
            return json_error("Inbox not found", 404)
        return jsonify({"ok": True})

    @app.get("/api/inboxes/<inbox_id>/files")
    def list_files(inbox_id: str):
        if not manager.get(inbox_id):
            return json_error("Inbox not found", 404)
        return jsonify({"ok": True, "files": manager.list_files(inbox_id)})

    @app.get("/api/inboxes/<inbox_id>/files/download")
    def download_file(inbox_id: str):
        relative_path = request.args.get("path", "")
        try:
            path = manager.safe_file(inbox_id, relative_path)
            return send_file(path, as_attachment=True, download_name=path.name)
        except (ValueError, FileNotFoundError):
            return json_error("File not found", 404)

    @app.delete("/api/inboxes/<inbox_id>/files")
    def delete_file(inbox_id: str):
        relative_path = request.args.get("path", "")
        try:
            manager.delete_file(inbox_id, relative_path)
            return jsonify({"ok": True})
        except (ValueError, FileNotFoundError):
            return json_error("File not found", 404)

    @app.get("/api/inboxes/<inbox_id>/logs")
    def logs(inbox_id: str):
        if not manager.get(inbox_id):
            return json_error("Inbox not found", 404)
        return jsonify({"ok": True, "logs": manager.log_tail(inbox_id)})

    @app.get("/api/inboxes/<inbox_id>/export")
    def export_config(inbox_id: str):
        try:
            path = manager.export_path(inbox_id)
            return send_file(path, as_attachment=True, download_name=f"oniondrop-{inbox_id}.json", mimetype="application/json")
        except KeyError:
            return json_error("Inbox not found", 404)
        except ValueError as exc:
            return json_error(str(exc), 409)

    @app.post("/api/import")
    def import_config():
        uploaded = request.files.get("config")
        if not uploaded:
            return json_error("No OnionShare configuration selected")
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
            return json_error("Inbox not found", 404)
        kind = request.args.get("kind", "url")
        value = inbox.get("private_key") if kind == "key" else inbox.get("url")
        if not value:
            return json_error("Value is not available yet", 409)
        image = qrcode.make(value, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
        output = io.BytesIO()
        image.save(output)
        output.seek(0)
        return send_file(output, mimetype="image/svg+xml", max_age=0)

    return app
