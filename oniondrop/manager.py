from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .preview import build_preview, direct_preview_kind, guessed_mime
from .store import JsonStore

ONION_RE = re.compile(r"http://([a-z2-7]{56}\.onion)", re.IGNORECASE)
PRIVATE_KEY_RE = re.compile(r"Private key:\s*([A-Z2-7]+)", re.IGNORECASE)
BOOTSTRAP_RE = re.compile(r"Bootstrapped\s+(\d+)%", re.IGNORECASE)


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


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


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


class ChecksumCache:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"version": 1, "files": {}})

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
                raise ValueError
            return payload
        except (OSError, ValueError, json.JSONDecodeError):
            return {"version": 1, "files": {}}

    def _write(self, payload: dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix="checksums-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
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

    @staticmethod
    def _key(inbox_id: str, relative_path: str) -> str:
        return f"{inbox_id}/{relative_path}"

    def get(self, inbox_id: str, relative_path: str, size: int, mtime_ns: int) -> str | None:
        with self.lock:
            record = self._read()["files"].get(self._key(inbox_id, relative_path))
            if not isinstance(record, dict):
                return None
            if record.get("size") != size or record.get("mtime_ns") != mtime_ns:
                return None
            value = record.get("sha256")
            return str(value) if isinstance(value, str) else None

    def put(self, inbox_id: str, relative_path: str, size: int, mtime_ns: int, sha256: str) -> None:
        with self.lock:
            payload = self._read()
            payload["files"][self._key(inbox_id, relative_path)] = {
                "size": size,
                "mtime_ns": mtime_ns,
                "sha256": sha256,
                "updated_at": iso_now(),
            }
            self._write(payload)

    def remove(self, inbox_id: str, relative_path: str | None = None) -> None:
        with self.lock:
            payload = self._read()
            prefix = f"{inbox_id}/"
            if relative_path is None:
                payload["files"] = {k: v for k, v in payload["files"].items() if not k.startswith(prefix)}
            else:
                payload["files"].pop(self._key(inbox_id, relative_path), None)
            self._write(payload)


class OnionDropManager:
    def __init__(self, data_root: Path, mock: bool = False):
        self.data_root = data_root
        self.mock = mock
        self.max_active = env_int("ONIONDROP_MAX_ACTIVE", 4, 1, 32)
        self.services_dir = data_root / "services"
        self.inboxes_dir = data_root / "inboxes"
        self.logs_dir = data_root / "logs"
        self.home_dir = data_root / "home"
        self.tmp_dir = data_root / "tmp"
        for path in (self.services_dir, self.inboxes_dir, self.logs_dir, self.home_dir, self.tmp_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.store = JsonStore(data_root / "state.json")
        self.checksums = ChecksumCache(data_root / "checksums.json")
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.reader_threads: dict[str, threading.Thread] = {}
        self.bootstrap_progress: dict[str, int] = {}
        self.lock = threading.RLock()
        self.shutdown_event = threading.Event()
        self._tor_version = self._detect_tor_version()
        self._migrate_inboxes()
        self.monitor_thread = threading.Thread(target=self._monitor, daemon=True, name="oniondrop-monitor")
        self.monitor_thread.start()
        self._install_signal_handlers()
        self._restore_autostart()

    def _detect_tor_version(self) -> str:
        if self.mock:
            return "mock"
        try:
            result = subprocess.run(["tor", "--version"], capture_output=True, text=True, timeout=5, check=False)
            first = (result.stdout or result.stderr).splitlines()[0].strip()
            match = re.search(r"Tor version\s+([^ .]+(?:\.[^ .]+)*)", first)
            return match.group(1).rstrip(".") if match else first[:80]
        except (OSError, subprocess.TimeoutExpired, IndexError):
            return "unknown"

    def _migrate_inboxes(self) -> None:
        defaults = {
            "description": "",
            "public": False,
            "allow_files": True,
            "allow_text": True,
            "autostart": True,
            "quota_mb": 0,
            "expires_at": None,
            "status": "offline",
            "url": None,
            "private_key": None,
            "last_error": None,
        }
        for inbox in self.store.list():
            changed = False
            for key, value in defaults.items():
                if key not in inbox:
                    inbox[key] = value
                    changed = True
            if changed:
                inbox["updated_at"] = iso_now()
                self.store.put(inbox)

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
                candidate = json.loads(path.read_text(encoding="utf-8"))
                existing = candidate if isinstance(candidate, dict) else {}
            except (OSError, json.JSONDecodeError):
                existing = {}

        # Keep all supported OnionShare settings from imported configurations,
        # but force the fields OnionDrop owns so the service cannot write outside
        # its inbox or silently change away from persistent receive mode.
        config = existing if existing else onionshare_config(
            name=inbox["name"],
            data_dir=self._inbox_path(inbox["id"]),
            public=bool(inbox["public"]),
            allow_files=bool(inbox["allow_files"]),
            allow_text=bool(inbox["allow_text"]),
        )
        config.setdefault("onion", {})
        config.setdefault("persistent", {})
        config.setdefault("general", {})
        config.setdefault("share", {})
        config.setdefault("receive", {})
        config.setdefault("website", {})
        config.setdefault("chat", {})
        config["persistent"].update(mode="receive", enabled=True, autostart_on_launch=False)
        config["general"]["title"] = inbox["name"]
        config["general"]["public"] = bool(inbox["public"])
        config["receive"]["data_dir"] = str(self._inbox_path(inbox["id"]))
        config["receive"]["disable_files"] = not bool(inbox["allow_files"])
        config["receive"]["disable_text"] = not bool(inbox["allow_text"])
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
        files = self.list_files(inbox["id"])
        decorated["bytes_used"] = sum(item["size"] for item in files)
        decorated["file_count"] = len(files)
        decorated["expired"] = self._is_expired(inbox)
        decorated["running"] = self.is_running(inbox["id"])
        decorated["tor_progress"] = self.bootstrap_progress.get(inbox["id"], 100 if decorated["status"] == "online" else 0)
        return decorated

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "Private inbox")).strip()[:80] or "Private inbox"
        allow_files = bool(payload.get("allow_files", True))
        allow_text = bool(payload.get("allow_text", True))
        if not allow_files and not allow_text:
            raise ValueError("at_least_one_type")
        inbox_id = uuid.uuid4().hex[:12]
        try:
            expires_hours = int(payload.get("expires_hours") or 0)
            quota_mb = int(payload.get("quota_mb") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_number") from exc
        expires_at = (utc_now() + timedelta(hours=expires_hours)).isoformat() if expires_hours > 0 else None
        inbox = {
            "id": inbox_id,
            "name": name,
            "description": str(payload.get("description", "")).strip()[:240],
            "public": bool(payload.get("public", False)),
            "allow_files": allow_files,
            "allow_text": allow_text,
            "autostart": bool(payload.get("autostart", True)),
            "quota_mb": max(0, min(quota_mb, 102400)),
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
        current = self.store.get(inbox_id)
        if not current:
            raise KeyError(inbox_id)
        inbox = dict(current)
        if "name" in payload:
            inbox["name"] = str(payload["name"]).strip()[:80] or inbox["name"]
        if "description" in payload:
            inbox["description"] = str(payload["description"]).strip()[:240]
        for key in ("public", "allow_files", "allow_text", "autostart"):
            if key in payload:
                inbox[key] = bool(payload[key])
        if not inbox["allow_files"] and not inbox["allow_text"]:
            raise ValueError("at_least_one_type")
        if "quota_mb" in payload:
            try:
                inbox["quota_mb"] = max(0, min(int(payload["quota_mb"] or 0), 102400))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_number") from exc

        # Validate the full update before interrupting a running OnionShare service.
        was_running = self.is_running(inbox_id)
        if was_running:
            self.stop(inbox_id)
        inbox["updated_at"] = iso_now()
        self.store.put(inbox)
        self._write_config(inbox, preserve_keys=True)
        if was_running:
            self.start(inbox_id)
        return self.get(inbox_id)  # type: ignore[return-value]

    def import_config(self, payload: bytes, name: str | None = None, autostart: bool = True) -> dict[str, Any]:
        if len(payload) > 1_000_000:
            raise ValueError("config_too_large")
        try:
            config = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_config") from exc
        if not isinstance(config, dict) or config.get("persistent", {}).get("mode") != "receive":
            raise ValueError("receive_config_only")
        onion_private_key = config.get("onion", {}).get("private_key")
        if not onion_private_key:
            raise ValueError("missing_onion_identity")
        allow_files = not bool(config.get("receive", {}).get("disable_files", False))
        allow_text = not bool(config.get("receive", {}).get("disable_text", False))
        if not allow_files and not allow_text:
            raise ValueError("at_least_one_type")

        inbox_id = uuid.uuid4().hex[:12]
        inbox_dir = self._inbox_path(inbox_id)
        config_path = self._config_path(inbox_id)
        inbox_dir.mkdir(parents=True, exist_ok=True)
        config.setdefault("persistent", {})["enabled"] = True
        config["persistent"]["mode"] = "receive"
        config["persistent"]["autostart_on_launch"] = False
        config.setdefault("receive", {})["data_dir"] = str(inbox_dir)
        private_key = config.get("onion", {}).get("client_auth_priv_key")
        service_id = config.get("general", {}).get("service_id")
        inbox = {
            "id": inbox_id,
            "name": str(name or config.get("general", {}).get("title") or "Imported inbox")[:80],
            "description": "Imported from an OnionShare persistent receive configuration.",
            "public": bool(config.get("general", {}).get("public", False)),
            "allow_files": allow_files,
            "allow_text": allow_text,
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
        try:
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            config_path.chmod(0o600)
            self.store.put(inbox)
            if autostart:
                self.start(inbox_id)
            return self.get(inbox_id)  # type: ignore[return-value]
        except Exception:
            if self.store.get(inbox_id):
                self.stop(inbox_id, persist_status=False)
                self.store.delete(inbox_id)
            config_path.unlink(missing_ok=True)
            shutil.rmtree(inbox_dir, ignore_errors=True)
            raise

    def export_path(self, inbox_id: str) -> Path:
        if not self.store.get(inbox_id):
            raise KeyError(inbox_id)
        path = self._config_path(inbox_id)
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("config_not_ready") from exc
        if not config.get("onion", {}).get("private_key"):
            raise ValueError("identity_not_ready")
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
                return self._patch(inbox_id, status="expired", last_error="expired")
            if self.is_running(inbox_id):
                return self.get(inbox_id)  # type: ignore[return-value]
            active_count = sum(1 for item in self.store.list() if self.is_running(item["id"]))
            if active_count >= self.max_active:
                raise ValueError("max_active_reached")
            self._write_config(inbox, preserve_keys=True)
            self.bootstrap_progress[inbox_id] = 5
            if self.mock:
                url = inbox.get("url") or f"http://{self._mock_onion()}.onion"
                key = None if inbox["public"] else (inbox.get("private_key") or self._mock_key())
                self.bootstrap_progress[inbox_id] = 100
                return self._patch(inbox_id, status="online", url=url, private_key=key, last_error=None)
            log_path = self._log_path(inbox_id)
            log_handle = log_path.open("a", encoding="utf-8")
            env = os.environ.copy()
            runtime_home = self.home_dir / inbox_id
            runtime_home.mkdir(parents=True, exist_ok=True)
            env["HOME"] = str(runtime_home)
            command = ["onionshare-cli", "--persistent", str(self._config_path(inbox_id)), "--verbose"]
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                    start_new_session=True,
                )
            except OSError:
                log_handle.close()
                self.bootstrap_progress.pop(inbox_id, None)
                raise
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
            self.bootstrap_progress.pop(inbox_id, None)
            if persist_status and self.store.get(inbox_id):
                return self._patch(inbox_id, status="offline", last_error=None)
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
            self.checksums.remove(inbox_id)
        return self.store.delete(inbox_id)

    def _consume_output(self, inbox_id: str, process: subprocess.Popen[str], log_handle: Any) -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                url_match = ONION_RE.search(line)
                key_match = PRIVATE_KEY_RE.search(line)
                bootstrap_match = BOOTSTRAP_RE.search(line)
                changes: dict[str, Any] = {}
                if bootstrap_match:
                    self.bootstrap_progress[inbox_id] = max(5, min(99, int(bootstrap_match.group(1))))
                if url_match:
                    changes["url"] = f"http://{url_match.group(1).lower()}"
                    changes["status"] = "online"
                    changes["last_error"] = None
                    self.bootstrap_progress[inbox_id] = 100
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
            self.bootstrap_progress.pop(inbox_id, None)
            inbox = self.store.get(inbox_id)
            if inbox and inbox.get("status") not in ("offline", "expired", "quota-reached"):
                error = None if code == 0 else "onionshare_exited"
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
                    self._patch(inbox_id, status="expired", last_error="expired")
                    continue
                quota_mb = int(inbox.get("quota_mb") or 0)
                if quota_mb > 0 and directory_size(self._inbox_path(inbox_id)) >= quota_mb * 1024 * 1024:
                    if self.is_running(inbox_id):
                        self.stop(inbox_id)
                    if inbox.get("status") != "quota-reached":
                        self._patch(inbox_id, status="quota-reached", last_error="storage_limit")
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
                relative = path.relative_to(root).as_posix()
                items.append(
                    {
                        "path": relative,
                        "name": filename,
                        "size": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                        "mime": guessed_mime(path),
                        "previewable": self.previewable(path),
                        "sha256": self.checksums.get(inbox_id, relative, stat.st_size, stat.st_mtime_ns),
                    }
                )
        return sorted(items, key=lambda item: item["modified_at"], reverse=True)

    @staticmethod
    def previewable(path: Path) -> bool:
        if direct_preview_kind(path):
            return True
        return path.suffix.lower() in {
            ".txt", ".md", ".markdown", ".rst", ".log", ".ini", ".cfg", ".conf", ".env",
            ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html", ".htm", ".xml",
            ".yaml", ".yml", ".toml", ".json", ".jsonl", ".csv", ".tsv", ".sql", ".sh",
            ".java", ".c", ".h", ".cpp", ".hpp", ".go", ".rs", ".php", ".rb", ".swift",
            ".kt", ".ics", ".vcf", ".srt", ".ass", ".svg", ".docx", ".xlsx", ".pptx",
            ".odt", ".ods", ".odp", ".epub", ".eml", ".rtf", ".zip", ".tar", ".gz",
            ".tgz", ".bz2", ".xz",
        }

    def safe_file(self, inbox_id: str, relative_path: str) -> Path:
        root = self._inbox_path(inbox_id).resolve()
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("invalid_path")
        if not candidate.is_file():
            raise FileNotFoundError(relative_path)
        return candidate

    def delete_file(self, inbox_id: str, relative_path: str) -> None:
        path = self.safe_file(inbox_id, relative_path)
        path.unlink()
        self.checksums.remove(inbox_id, relative_path)
        root = self._inbox_path(inbox_id)
        parent = path.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def checksum_file(self, inbox_id: str, relative_path: str) -> str:
        path = self.safe_file(inbox_id, relative_path)
        stat = path.stat()
        cached = self.checksums.get(inbox_id, relative_path, stat.st_size, stat.st_mtime_ns)
        if cached:
            return cached
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        value = digest.hexdigest()
        stat_after = path.stat()
        if stat_after.st_size == stat.st_size and stat_after.st_mtime_ns == stat.st_mtime_ns:
            self.checksums.put(inbox_id, relative_path, stat.st_size, stat.st_mtime_ns, value)
        return value

    def preview(self, inbox_id: str, relative_path: str, inline_url: str) -> dict[str, Any]:
        path = self.safe_file(inbox_id, relative_path)
        return build_preview(path, inline_url)

    def create_zip(self, inbox_id: str, paths: list[str]) -> Path:
        if not paths:
            raise ValueError("no_files_selected")
        unique_paths = list(dict.fromkeys(str(item) for item in paths))
        if len(unique_paths) > 1000:
            raise ValueError("too_many_files")
        fd, tmp_name = tempfile.mkstemp(prefix=f"oniondrop-{inbox_id}-", suffix=".zip", dir=self.tmp_dir)
        os.close(fd)
        output = Path(tmp_name)
        try:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for relative_path in unique_paths:
                    path = self.safe_file(inbox_id, relative_path)
                    archive.write(path, arcname=relative_path)
            return output
        except Exception:
            output.unlink(missing_ok=True)
            raise

    def log_tail(self, inbox_id: str, lines: int = 200) -> str:
        path = self._log_path(inbox_id)
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(content[-max(1, min(lines, 1000)):])
        except OSError:
            return ""

    def tor_status(self) -> dict[str, Any]:
        inboxes = self.store.list()
        statuses = [str(item.get("status", "offline")) for item in inboxes]
        active_services = sum(1 for status in statuses if status == "online")
        connecting_services = sum(1 for status in statuses if status == "starting")
        error_services = sum(1 for status in statuses if status == "error")
        if active_services:
            state = "connected"
            progress = 100
        elif connecting_services:
            state = "connecting"
            progress = max([self.bootstrap_progress.get(item["id"], 5) for item in inboxes if item.get("status") == "starting"] or [5])
        elif error_services:
            state = "error"
            progress = 0
        else:
            state = "idle"
            progress = 0
        return {
            "state": state,
            "progress": progress,
            "active_services": active_services,
            "connecting_services": connecting_services,
            "error_services": error_services,
            "tor_version": self._tor_version,
            "mock": self.mock,
            "checked_at": iso_now(),
        }

    @staticmethod
    def _mock_onion() -> str:
        return base64.b32encode(secrets.token_bytes(35)).decode("ascii").lower().rstrip("=")[:56]

    @staticmethod
    def _mock_key() -> str:
        return base64.b32encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
