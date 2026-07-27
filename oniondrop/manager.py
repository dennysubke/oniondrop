from __future__ import annotations

import base64
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .store import JsonStore

ONION_RE = re.compile(r"http://([a-z2-7]{56}\.onion)", re.IGNORECASE)
PRIVATE_KEY_RE = re.compile(r"Private key:\s*([A-Z2-7]+)", re.IGNORECASE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _, files in os.walk(path):
        for filename in files:
            try:
                total += (Path(root) / filename).stat().st_size
            except OSError:
                pass
    return total


def onionshare_config(
    *, name: str, data_dir: Path, public: bool, allow_files: bool, allow_text: bool
) -> dict[str, Any]:
    return {
        "onion": {
            "private_key": None,
            "client_auth_priv_key": None,
            "client_auth_pub_key": None,
        },
        "persistent": {
            "mode": "receive",
            "enabled": True,
            "autostart_on_launch": False,
        },
        "general": {
            "title": name,
            "public": public,
            "autostart_timer": 0,
            "autostop_timer": 0,
            "service_id": None,
            "qr": False,
        },
        "share": {
            "autostop_sharing": True,
            "filenames": [],
            "log_filenames": False,
        },
        "receive": {
            "data_dir": str(data_dir),
            "webhook_url": None,
            "disable_text": not allow_text,
            "disable_files": not allow_files,
        },
        "website": {
            "disable_csp": False,
            "custom_csp": None,
            "log_filenames": False,
            "filenames": [],
        },
        "chat": {},
    }


class OnionDropManager:
    def __init__(self, data_root: Path, mock: bool = False):
        self.data_root = data_root
        self.mock = mock
        self.max_active = max(1, int(os.environ.get("ONIONDROP_MAX_ACTIVE", "4")))
        self.services_dir = data_root / "services"
        self.inboxes_dir = data_root / "inboxes"
        self.logs_dir = data_root / "logs"
        self.home_dir = data_root / "home"
        for path in (self.services_dir, self.inboxes_dir, self.logs_dir, self.home_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.store = JsonStore(data_root / "state.json")
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.reader_threads: dict[str, threading.Thread] = {}
        self.lock = threading.RLock()
        self.shutdown_event = threading.Event()
        self.monitor_thread = threading.Thread(target=self._monitor, daemon=True, name="oniondrop-monitor")
        self.monitor_thread.start()
        self._install_signal_handlers()
        self._restore_autostart()

    def _install_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(signum, self._signal_shutdown)
            except (ValueError, OSError):
                pass

    def _signal_shutdown(self, signum: int, frame: object) -> None:
        self.shutdown()
        raise SystemExit(128 + signum)

    def shutdown(self) -> None:
        self.shutdown_event.set()
        for inbox_id in list(self.processes):
            self.stop(inbox_id, persist_status=False)

    def _restore_autostart(self) -> None:
        def delayed_start() -> None:
            time.sleep(0.4)
            for inbox in self.store.list():
                if inbox.get("autostart") and not self._is_expired(inbox):
                    try:
                        self.start(inbox["id"])
                    except Exception as exc:  # noqa: BLE001
                        self._patch(inbox["id"], status="error", last_error=str(exc))
        threading.Thread(target=delayed_start, daemon=True, name="oniondrop-autostart").start()

    def _config_path(self, inbox_id: str) -> Path:
        return self.services_dir / f"{inbox_id}.json"

    def _inbox_path(self, inbox_id: str) -> Path:
        return self.inboxes_dir / inbox_id

    def _log_path(self, inbox_id: str) -> Path:
        return self.logs_dir / f"{inbox_id}.log"

    def _patch(self, inbox_id: str, **changes: Any) -> dict[str, Any]:
        inbox = self.store.get(inbox_id)
        if not inbox:
            raise KeyError(inbox_id)
        inbox.update(changes)
        inbox["updated_at"] = iso_now()
        return self.store.put(inbox)

    def _write_config(self, inbox: dict[str, Any], preserve_keys: bool = True) -> None:
        path = self._config_path(inbox["id"])
        existing: dict[str, Any] = {}
        if preserve_keys and path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        config = onionshare_config(
            name=inbox["name"],
            data_dir=self._inbox_path(inbox["id"]),
            public=bool(inbox["public"]),
            allow_files=bool(inbox["allow_files"]),
            allow_text=bool(inbox["allow_text"]),
        )
        if preserve_keys:
            for group, keys in {
                "onion": ("private_key", "client_auth_priv_key", "client_auth_pub_key"),
                "general": ("service_id",),
            }.items():
                for key in keys:
                    if existing.get(group, {}).get(key):
                        config[group][key] = existing[group][key]
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def list(self) -> list[dict[str, Any]]:
        return [self._decorate(item) for item in self.store.list()]

    def get(self, inbox_id: str) -> dict[str, Any] | None:
        item = self.store.get(inbox_id)
        return self._decorate(item) if item else None

    def _decorate(self, inbox: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(inbox)
        decorated["bytes_used"] = directory_size(self._inbox_path(inbox["id"]))
        decorated["file_count"] = len(self.list_files(inbox["id"]))
        decorated["expired"] = self._is_expired(inbox)
        decorated["running"] = self.is_running(inbox["id"])
        return decorated

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "Private inbox")).strip()[:80] or "Private inbox"
        allow_files = bool(payload.get("allow_files", True))
        allow_text = bool(payload.get("allow_text", True))
        if not allow_files and not allow_text:
            raise ValueError("At least files or text messages must be enabled")
        inbox_id = uuid.uuid4().hex[:12]
        expires_hours = int(payload.get("expires_hours") or 0)
        expires_at = (utc_now() + timedelta(hours=expires_hours)).isoformat() if expires_hours > 0 else None
        inbox = {
            "id": inbox_id,
            "name": name,
            "description": str(payload.get("description", "")).strip()[:240],
            "public": bool(payload.get("public", False)),
            "allow_files": allow_files,
            "allow_text": allow_text,
            "autostart": bool(payload.get("autostart", True)),
            "quota_mb": max(0, min(int(payload.get("quota_mb") or 0), 102400)),
            "expires_at": expires_at,
            "status": "offline",
            "url": None,
            "private_key": None,
            "last_error": None,
            "created_at": iso_now(),
            "updated_at": iso_now(),
        }
        self._inbox_path(inbox_id).mkdir(parents=True, exist_ok=True)
        self._write_config(inbox, preserve_keys=False)
        self.store.put(inbox)
        if bool(payload.get("start_now", True)):
            self.start(inbox_id)
        return self.get(inbox_id)  # type: ignore[return-value]

    def update(self, inbox_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        inbox = self.store.get(inbox_id)
        if not inbox:
            raise KeyError(inbox_id)
        was_running = self.is_running(inbox_id)
        if was_running:
            self.stop(inbox_id)
        if "name" in payload:
            inbox["name"] = str(payload["name"]).strip()[:80] or inbox["name"]
        if "description" in payload:
            inbox["description"] = str(payload["description"]).strip()[:240]
        for key in ("public", "allow_files", "allow_text", "autostart"):
            if key in payload:
                inbox[key] = bool(payload[key])
        if not inbox["allow_files"] and not inbox["allow_text"]:
            raise ValueError("At least files or text messages must be enabled")
        if "quota_mb" in payload:
            inbox["quota_mb"] = max(0, min(int(payload["quota_mb"] or 0), 102400))
        inbox["updated_at"] = iso_now()
        self.store.put(inbox)
        self._write_config(inbox, preserve_keys=True)
        if was_running:
            self.start(inbox_id)
        return self.get(inbox_id)  # type: ignore[return-value]

    def import_config(self, payload: bytes, name: str | None = None, autostart: bool = True) -> dict[str, Any]:
        if len(payload) > 1_000_000:
            raise ValueError("Configuration file is too large")
        try:
            config = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid OnionShare JSON configuration") from exc
        if config.get("persistent", {}).get("mode") != "receive":
            raise ValueError("Only persistent OnionShare receive configurations can be imported")
        onion_private_key = config.get("onion", {}).get("private_key")
        if not onion_private_key:
            raise ValueError("This configuration has no persistent onion private key. Start it once in OnionShare before importing.")
        inbox_id = uuid.uuid4().hex[:12]
        inbox_dir = self._inbox_path(inbox_id)
        inbox_dir.mkdir(parents=True, exist_ok=True)
        config.setdefault("persistent", {})["enabled"] = True
        config["persistent"]["mode"] = "receive"
        config["persistent"]["autostart_on_launch"] = False
        config.setdefault("receive", {})["data_dir"] = str(inbox_dir)
        config_path = self._config_path(inbox_id)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        config_path.chmod(0o600)
        private_key = config.get("onion", {}).get("client_auth_priv_key")
        service_id = config.get("general", {}).get("service_id")
        inbox = {
            "id": inbox_id,
            "name": str(name or config.get("general", {}).get("title") or "Imported inbox")[:80],
            "description": "Imported from an OnionShare persistent receive configuration.",
            "public": bool(config.get("general", {}).get("public", False)),
            "allow_files": not bool(config.get("receive", {}).get("disable_files", False)),
            "allow_text": not bool(config.get("receive", {}).get("disable_text", False)),
            "autostart": autostart,
            "quota_mb": 0,
            "expires_at": None,
            "status": "offline",
            "url": f"http://{service_id}.onion" if service_id else None,
            "private_key": private_key,
            "last_error": None,
            "created_at": iso_now(),
            "updated_at": iso_now(),
        }
        self.store.put(inbox)
        if autostart:
            self.start(inbox_id)
        return self.get(inbox_id)  # type: ignore[return-value]

    def export_path(self, inbox_id: str) -> Path:
        if not self.store.get(inbox_id):
            raise KeyError(inbox_id)
        path = self._config_path(inbox_id)
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("The OnionShare configuration is not ready") from exc
        if not config.get("onion", {}).get("private_key"):
            raise ValueError("Start this inbox once before exporting its OnionShare identity")
        return path

    def is_running(self, inbox_id: str) -> bool:
        if self.mock:
            inbox = self.store.get(inbox_id)
            return bool(inbox and inbox.get("status") == "online")
        process = self.processes.get(inbox_id)
        return bool(process and process.poll() is None)

    def start(self, inbox_id: str) -> dict[str, Any]:
        with self.lock:
            inbox = self.store.get(inbox_id)
            if not inbox:
                raise KeyError(inbox_id)
            if self._is_expired(inbox):
                return self._patch(inbox_id, status="expired", last_error="This inbox has expired")
            if self.is_running(inbox_id):
                return self.get(inbox_id)  # type: ignore[return-value]
            active_count = sum(1 for item in self.store.list() if self.is_running(item["id"]))
            if active_count >= self.max_active:
                raise ValueError(f"At most {self.max_active} inboxes can be active at once")
            self._write_config(inbox, preserve_keys=True)
            if self.mock:
                url = inbox.get("url") or f"http://{self._mock_onion()}.onion"
                key = None if inbox["public"] else (inbox.get("private_key") or self._mock_key())
                return self._patch(inbox_id, status="online", url=url, private_key=key, last_error=None)
            log_path = self._log_path(inbox_id)
            log_handle = log_path.open("a", encoding="utf-8")
            env = os.environ.copy()
            runtime_home = self.home_dir / inbox_id
            runtime_home.mkdir(parents=True, exist_ok=True)
            env["HOME"] = str(runtime_home)
            command = ["onionshare-cli", "--persistent", str(self._config_path(inbox_id)), "--verbose"]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
            self.processes[inbox_id] = process
            self._patch(inbox_id, status="starting", last_error=None)
            thread = threading.Thread(
                target=self._consume_output,
                args=(inbox_id, process, log_handle),
                daemon=True,
                name=f"oniondrop-reader-{inbox_id}",
            )
            self.reader_threads[inbox_id] = thread
            thread.start()
            return self.get(inbox_id)  # type: ignore[return-value]

    def stop(self, inbox_id: str, persist_status: bool = True) -> dict[str, Any] | None:
        with self.lock:
            process = self.processes.pop(inbox_id, None)
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=12)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if persist_status and self.store.get(inbox_id):
                return self._patch(inbox_id, status="offline")
            return self.get(inbox_id)

    def delete(self, inbox_id: str, delete_files: bool = True) -> bool:
        if not self.store.get(inbox_id):
            return False
        self.stop(inbox_id)
        for path in (self._config_path(inbox_id), self._log_path(inbox_id)):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if delete_files:
            shutil.rmtree(self._inbox_path(inbox_id), ignore_errors=True)
        return self.store.delete(inbox_id)

    def _consume_output(self, inbox_id: str, process: subprocess.Popen[str], log_handle: Any) -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                url_match = ONION_RE.search(line)
                key_match = PRIVATE_KEY_RE.search(line)
                changes: dict[str, Any] = {}
                if url_match:
                    changes["url"] = f"http://{url_match.group(1).lower()}"
                    changes["status"] = "online"
                if key_match:
                    changes["private_key"] = key_match.group(1).upper()
                if changes and self.store.get(inbox_id):
                    self._patch(inbox_id, **changes)
                self._refresh_identity_from_config(inbox_id)
        finally:
            log_handle.close()
            code = process.poll()
            if self.processes.get(inbox_id) is process:
                self.processes.pop(inbox_id, None)
            inbox = self.store.get(inbox_id)
            if inbox and inbox.get("status") not in ("offline", "expired", "quota-reached"):
                error = None if code == 0 else f"OnionShare exited with code {code}"
                self._patch(inbox_id, status="offline" if code == 0 else "error", last_error=error)

    def _refresh_identity_from_config(self, inbox_id: str) -> None:
        path = self._config_path(inbox_id)
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        changes: dict[str, Any] = {}
        service_id = config.get("general", {}).get("service_id")
        private_key = config.get("onion", {}).get("client_auth_priv_key")
        if service_id:
            changes["url"] = f"http://{service_id}.onion"
            changes["status"] = "online"
        if private_key:
            changes["private_key"] = private_key
        if changes and self.store.get(inbox_id):
            current = self.store.get(inbox_id) or {}
            if any(current.get(key) != value for key, value in changes.items()):
                self._patch(inbox_id, **changes)

    def _monitor(self) -> None:
        while not self.shutdown_event.wait(2):
            for inbox in self.store.list():
                inbox_id = inbox["id"]
                if self._is_expired(inbox) and inbox.get("status") != "expired":
                    self.stop(inbox_id)
                    self._patch(inbox_id, status="expired", last_error="This inbox has expired")
                    continue
                quota_mb = int(inbox.get("quota_mb") or 0)
                if quota_mb > 0 and directory_size(self._inbox_path(inbox_id)) >= quota_mb * 1024 * 1024:
                    if self.is_running(inbox_id):
                        self.stop(inbox_id)
                    if inbox.get("status") != "quota-reached":
                        self._patch(inbox_id, status="quota-reached", last_error="Storage limit reached")
                if not self.mock:
                    process = self.processes.get(inbox_id)
                    if process and process.poll() is not None:
                        self.processes.pop(inbox_id, None)

    def _is_expired(self, inbox: dict[str, Any]) -> bool:
        expires_at = parse_iso(inbox.get("expires_at"))
        return bool(expires_at and utc_now() >= expires_at)

    def list_files(self, inbox_id: str) -> list[dict[str, Any]]:
        if not self.store.get(inbox_id):
            return []
        root = self._inbox_path(inbox_id)
        items: list[dict[str, Any]] = []
        for current_root, _, files in os.walk(root):
            for filename in files:
                path = Path(current_root) / filename
                try:
                    stat = path.stat()
                except OSError:
                    continue
                items.append({
                    "path": path.relative_to(root).as_posix(),
                    "name": filename,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                })
        return sorted(items, key=lambda item: item["modified_at"], reverse=True)

    def safe_file(self, inbox_id: str, relative_path: str) -> Path:
        root = self._inbox_path(inbox_id).resolve()
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("Invalid path")
        if not candidate.is_file():
            raise FileNotFoundError(relative_path)
        return candidate

    def delete_file(self, inbox_id: str, relative_path: str) -> None:
        path = self.safe_file(inbox_id, relative_path)
        path.unlink()
        root = self._inbox_path(inbox_id)
        parent = path.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def log_tail(self, inbox_id: str, lines: int = 200) -> str:
        path = self._log_path(inbox_id)
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(content[-max(1, min(lines, 1000)):])
        except OSError:
            return ""

    @staticmethod
    def _mock_onion() -> str:
        return base64.b32encode(secrets.token_bytes(35)).decode("ascii").lower().rstrip("=")[:56]

    @staticmethod
    def _mock_key() -> str:
        return base64.b32encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
