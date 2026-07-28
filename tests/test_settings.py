from __future__ import annotations

import json
from pathlib import Path

import pytest

from oniondrop.settings import SettingsManager, check_password_hash, generate_password_hash


def test_scrypt_password_hash_roundtrip() -> None:
    encoded = generate_password_hash("correct horse battery staple")
    assert encoded.startswith("scrypt$16384$8$1$")
    assert check_password_hash(encoded, "correct horse battery staple")
    assert not check_password_hash(encoded, "wrong password")
    assert not check_password_hash("invalid", "anything")
    assert not check_password_hash(encoded, "x" * 257)
    with pytest.raises(ValueError, match="password_too_long"):
        generate_password_hash("x" * 257)


def test_first_run_setup_and_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONIONDROP_AUTH_MODE", "setup")
    manager = SettingsManager(tmp_path / "settings.json")
    assert manager.public() == {
        "configured": False,
        "auth_enabled": False,
        "username": "admin",
        "default_language": "en",
    }

    configured = manager.configure(
        {
            "auth_enabled": True,
            "username": "denny",
            "password": "a very safe password",
            "default_language": "de",
        }
    )
    assert configured["configured"] is True
    assert configured["auth_enabled"] is True
    assert configured["default_language"] == "de"
    assert manager.verify("denny", "a very safe password")
    assert not manager.verify("denny", "wrong password")

    with pytest.raises(ValueError, match="current_password_invalid"):
        manager.update({"auth_enabled": False}, current_password="wrong")

    updated = manager.update(
        {"auth_enabled": True, "username": "denny", "default_language": "fr"},
        current_password="",
    )
    assert updated["default_language"] == "fr"

    disabled = manager.update({"auth_enabled": False}, current_password="a very safe password")
    assert disabled["auth_enabled"] is False
    assert not manager.verify("denny", "a very safe password")

    with pytest.raises(ValueError, match="password_too_short"):
        manager.update({"auth_enabled": True, "new_password": "short"})

    enabled = manager.update({"auth_enabled": True, "new_password": "another safe password"})
    assert enabled["auth_enabled"] is True
    assert manager.verify("denny", "another safe password")

    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert raw["password_hash"].startswith("scrypt$")
    assert raw["session_secret"]


def test_disabled_environment_mode_is_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONIONDROP_AUTH_MODE", "disabled")
    monkeypatch.setenv("ONIONDROP_DEFAULT_LANGUAGE", "ja")
    manager = SettingsManager(tmp_path / "settings.json")
    assert manager.public()["configured"] is True
    assert manager.public()["auth_enabled"] is False
    assert manager.public()["default_language"] == "ja"


def test_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONIONDROP_AUTH_MODE", "setup")
    manager = SettingsManager(tmp_path / "settings.json")
    with pytest.raises(ValueError, match="invalid_username"):
        manager.configure({"auth_enabled": False, "username": "x"})
    with pytest.raises(ValueError, match="password_too_short"):
        manager.configure({"auth_enabled": True, "username": "admin", "password": "short"})
    with pytest.raises(ValueError, match="password_too_long"):
        manager.configure({"auth_enabled": True, "username": "admin", "password": "x" * 257})
