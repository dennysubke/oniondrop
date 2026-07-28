from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "oniondrop" / "static" / "i18n"


def test_all_translations_have_identical_nonempty_keys() -> None:
    payloads = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(I18N.glob("*.json"))}
    assert set(payloads) == {"en", "de", "es", "it", "fr", "zh", "ja", "ru"}
    reference = set(payloads["en"])
    assert len(reference) >= 180
    for language, payload in payloads.items():
        assert set(payload) == reference, language
        assert all(isinstance(value, str) and value.strip() for value in payload.values()), language


def test_template_translation_keys_exist() -> None:
    english = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
    html = (ROOT / "oniondrop" / "templates" / "index.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'data-i18n(?:-placeholder|-title)?="([^"]+)"', html))
    assert keys <= set(english)


def test_compose_files_parse_and_are_platform_neutral() -> None:
    for name in ("docker-compose.yml", "docker-compose.dev.yml"):
        payload = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        assert payload["version"] == "3.7"
        assert "oniondrop" in payload["services"]
    production_paths = [ROOT / "oniondrop", ROOT / "Dockerfile", ROOT / "docker-compose.yml", ROOT / "docker-compose.dev.yml"]
    files = []
    for item in production_paths:
        files.extend(item.rglob("*") if item.is_dir() else [item])
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in files
        if path.is_file() and path.suffix.lower() not in {".png"}
    )
    assert "Umbrel" not in source_text
    assert "0.1.0" not in source_text


def test_language_picker_uses_local_discreet_flag_assets() -> None:
    flags = ROOT / "oniondrop" / "static" / "flags"
    assert {path.name for path in flags.glob("*.svg")} == {
        "gb.svg", "de.svg", "es.svg", "it.svg", "fr.svg", "cn.svg", "jp.svg", "ru.svg"
    }
    app_js = (ROOT / "oniondrop" / "static" / "app.js").read_text(encoding="utf-8")
    assert "language-picker-option" in app_js
    assert "/static/flags/gb.svg" in app_js
    assert "🇬🇧" not in app_js


def test_private_key_copy_is_resolved_from_inbox_state() -> None:
    app_js = (ROOT / "oniondrop" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-copy-field="private_key"' in app_js
    assert '["url", "private_key"].includes(field)' in app_js
    assert 'value = inbox[field] || ""' in app_js
