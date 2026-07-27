from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"version": 1, "inboxes": []})

    def _read(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or not isinstance(payload.get("inboxes"), list):
                raise ValueError("Invalid state structure")
            return payload
        except (OSError, ValueError, json.JSONDecodeError):
            return {"version": 1, "inboxes": []}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            return deepcopy(self._read()["inboxes"])

    def get(self, inbox_id: str) -> dict[str, Any] | None:
        with self.lock:
            return next((deepcopy(item) for item in self._read()["inboxes"] if item["id"] == inbox_id), None)

    def put(self, inbox: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            payload = self._read()
            replaced = False
            for index, existing in enumerate(payload["inboxes"]):
                if existing["id"] == inbox["id"]:
                    payload["inboxes"][index] = deepcopy(inbox)
                    replaced = True
                    break
            if not replaced:
                payload["inboxes"].append(deepcopy(inbox))
            self._write(payload)
            return deepcopy(inbox)

    def delete(self, inbox_id: str) -> bool:
        with self.lock:
            payload = self._read()
            original = len(payload["inboxes"])
            payload["inboxes"] = [item for item in payload["inboxes"] if item["id"] != inbox_id]
            if len(payload["inboxes"]) == original:
                return False
            self._write(payload)
            return True
