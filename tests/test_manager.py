from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path

import pytest

from oniondrop.manager import OnionDropManager, onionshare_config


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ONIONDROP_MAX_ACTIVE", "4")
    instance = OnionDropManager(tmp_path, mock=True)
    yield instance
    instance.shutdown()


def test_inbox_lifecycle_and_tor_status(manager: OnionDropManager) -> None:
    inbox = manager.create(
        {
            "name": "Documents",
            "description": "Secure documents",
            "allow_files": True,
            "allow_text": True,
            "public": False,
            "autostart": False,
            "start_now": True,
        }
    )
    assert inbox["status"] == "online"
    assert inbox["url"].startswith("http://") and inbox["url"].endswith(".onion")
    assert inbox["private_key"]
    status = manager.tor_status()
    assert status["state"] == "connected"
    assert status["progress"] == 100
    assert status["active_services"] == 1

    stopped = manager.stop(inbox["id"])
    assert stopped and stopped["status"] == "offline"
    assert manager.tor_status()["state"] == "idle"

    restarted = manager.start(inbox["id"])
    assert restarted["url"] == inbox["url"]
    assert restarted["private_key"] == inbox["private_key"]

    assert manager.delete(inbox["id"])
    assert manager.get(inbox["id"]) is None


def test_update_validation_does_not_stop_running_service(manager: OnionDropManager) -> None:
    inbox = manager.create({"name": "Inbox", "autostart": False, "start_now": True})
    with pytest.raises(ValueError, match="at_least_one_type"):
        manager.update(inbox["id"], {"allow_files": False, "allow_text": False})
    assert manager.is_running(inbox["id"])
    current = manager.get(inbox["id"])
    assert current and current["allow_files"] and current["allow_text"]


def test_import_preserves_onionshare_configuration(manager: OnionDropManager) -> None:
    config = onionshare_config(
        name="Imported",
        data_dir=Path("/tmp/ignored"),
        public=False,
        allow_files=True,
        allow_text=False,
    )
    config["onion"]["private_key"] = "ED25519-V3:EXAMPLE"
    config["onion"]["client_auth_priv_key"] = "PRIVATEACCESSKEY"
    config["general"]["service_id"] = "a" * 56
    config["receive"]["webhook_url"] = "https://example.invalid/hook"
    config["custom_extension"] = {"keep": True}

    inbox = manager.import_config(json.dumps(config).encode(), autostart=False)
    assert inbox["url"] == f"http://{'a' * 56}.onion"
    manager.start(inbox["id"])
    exported = json.loads(manager.export_path(inbox["id"]).read_text(encoding="utf-8"))
    assert exported["custom_extension"] == {"keep": True}
    assert exported["receive"]["webhook_url"] == "https://example.invalid/hook"
    assert exported["receive"]["data_dir"].endswith(f"/inboxes/{inbox['id']}")
    assert exported["persistent"]["mode"] == "receive"


def test_file_hash_zip_preview_and_safe_paths(manager: OnionDropManager) -> None:
    inbox = manager.create({"name": "Files", "autostart": False, "start_now": False})
    root = manager.inboxes_dir / inbox["id"]
    (root / "nested").mkdir(parents=True)
    first = root / "hello.txt"
    second = root / "nested" / "data.json"
    first.write_text("hello oniondrop", encoding="utf-8")
    second.write_text('{"value": 42}', encoding="utf-8")

    files = manager.list_files(inbox["id"])
    assert {item["path"] for item in files} == {"hello.txt", "nested/data.json"}
    assert all(item["previewable"] for item in files)

    expected = hashlib.sha256(first.read_bytes()).hexdigest()
    assert manager.checksum_file(inbox["id"], "hello.txt") == expected
    assert manager.checksum_file(inbox["id"], "hello.txt") == expected
    cached = {item["path"]: item for item in manager.list_files(inbox["id"])}
    assert cached["hello.txt"]["sha256"] == expected

    preview = manager.preview(inbox["id"], "nested/data.json", "/inline")
    assert preview["kind"] == "text"
    assert '"value": 42' in preview["content"]

    output = manager.create_zip(inbox["id"], ["hello.txt", "nested/data.json", "hello.txt"])
    try:
        with zipfile.ZipFile(output) as archive:
            assert archive.namelist() == ["hello.txt", "nested/data.json"]
            assert archive.read("hello.txt") == b"hello oniondrop"
    finally:
        output.unlink(missing_ok=True)

    with pytest.raises(ValueError, match="invalid_path"):
        manager.safe_file(inbox["id"], "../../etc/passwd")

    manager.delete_file(inbox["id"], "hello.txt")
    assert not first.exists()


def test_expiration_and_quota(manager: OnionDropManager) -> None:
    expired = manager.create({"name": "Expiring", "expires_hours": -1, "autostart": False, "start_now": False})
    # Negative values intentionally mean no expiry.
    assert expired["expired"] is False

    limited = manager.create({"name": "Limited", "quota_mb": 1, "autostart": False, "start_now": True})
    root = manager.inboxes_dir / limited["id"]
    (root / "large.bin").write_bytes(b"x" * (1024 * 1024 + 1))
    deadline = time.time() + 5
    while time.time() < deadline:
        current = manager.get(limited["id"])
        if current and current["status"] == "quota-reached":
            break
        time.sleep(0.1)
    current = manager.get(limited["id"])
    assert current and current["status"] == "quota-reached"


def test_legacy_inbox_metadata_is_migrated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONIONDROP_MAX_ACTIVE", "4")
    legacy = {
        "version": 1,
        "inboxes": [
            {
                "id": "legacy123456",
                "name": "Legacy inbox",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ],
    }
    (tmp_path / "state.json").write_text(json.dumps(legacy), encoding="utf-8")
    instance = OnionDropManager(tmp_path, mock=True)
    try:
        migrated = instance.get("legacy123456")
        assert migrated
        assert migrated["allow_files"] is True
        assert migrated["allow_text"] is True
        assert migrated["public"] is False
        assert migrated["status"] == "offline"
    finally:
        instance.shutdown()
