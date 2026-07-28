from __future__ import annotations

import csv
import io
import json
import mimetypes
import re
import tarfile
import zipfile
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MAX_TEXT_BYTES = 512 * 1024
MAX_STRUCTURED_BYTES = 20 * 1024 * 1024
MAX_ROWS = 120
MAX_COLUMNS = 30
MAX_ARCHIVE_ITEMS = 500
MAX_ZIP_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 32 * 1024 * 1024

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".avif"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac", ".flac", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".m4v"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".ini", ".cfg", ".conf", ".env",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html", ".htm", ".xml",
    ".yaml", ".yml", ".toml", ".jsonl", ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat",
    ".java", ".c", ".h", ".cpp", ".hpp", ".go", ".rs", ".php", ".rb", ".swift", ".kt",
    ".properties", ".ics", ".vcf", ".srt", ".ass",
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def guessed_mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def direct_preview_kind(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def _read_text(path: Path, limit: int = MAX_TEXT_BYTES) -> tuple[str, bool]:
    raw = path.read_bytes()[: limit + 1]
    truncated = len(raw) > limit
    raw = raw[:limit]
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), truncated
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), truncated


def _xml_text(raw: bytes, tags: set[str] | None = None) -> str:
    root = ET.fromstring(raw)
    values: list[str] = []
    for node in root.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if node.text and node.text.strip() and (tags is None or local in tags):
            values.append(node.text.strip())
    return "\n".join(values)



def _safe_zip_read(archive: zipfile.ZipFile, name: str, *, limit: int = MAX_ZIP_MEMBER_BYTES) -> bytes:
    """Read a known ZIP member while rejecting oversized decompressed payloads."""
    info = archive.getinfo(name)
    if info.is_dir() or info.file_size > limit:
        raise ValueError("archive_member_too_large")
    with archive.open(info, "r") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("archive_member_too_large")
    return data


def _safe_zip_names(archive: zipfile.ZipFile, predicate, *, maximum: int) -> list[str]:
    selected: list[str] = []
    total = 0
    for info in archive.infolist():
        if not info.is_dir() and predicate(info.filename):
            if info.file_size > MAX_ZIP_MEMBER_BYTES:
                continue
            total += info.file_size
            if total > MAX_ZIP_TOTAL_BYTES:
                break
            selected.append(info.filename)
            if len(selected) >= maximum:
                break
    return selected

def _docx_preview(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        raw = _safe_zip_read(archive, "word/document.xml")
    return {"kind": "document", "content": _xml_text(raw, {"t"})[:200_000], "format": "DOCX"}


def _pptx_preview(path: Path) -> dict[str, Any]:
    slides: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(_safe_zip_names(archive, lambda name: bool(re.fullmatch(r"ppt/slides/slide\d+\.xml", name)), maximum=80))
        for index, name in enumerate(names, start=1):
            text = _xml_text(_safe_zip_read(archive, name), {"t"})
            if text:
                slides.append(f"Slide {index}\n{text}")
    return {"kind": "document", "content": "\n\n".join(slides)[:250_000], "format": "PPTX"}


def _xlsx_preview(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(_safe_zip_read(archive, "xl/sharedStrings.xml"))
            for item in root:
                texts = [node.text or "" for node in item.iter() if node.tag.rsplit("}", 1)[-1] == "t"]
                shared.append("".join(texts))
        sheet_names = sorted(_safe_zip_names(archive, lambda name: bool(re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)), maximum=5))
        tables: list[dict[str, Any]] = []
        for sheet_index, sheet_name in enumerate(sheet_names[:5], start=1):
            root = ET.fromstring(_safe_zip_read(archive, sheet_name))
            rows: list[list[str]] = []
            for row in root.iter():
                if row.tag.rsplit("}", 1)[-1] != "row":
                    continue
                values: list[str] = []
                for cell in row:
                    if cell.tag.rsplit("}", 1)[-1] != "c":
                        continue
                    kind = cell.attrib.get("t")
                    value_node = next((node for node in cell if node.tag.rsplit("}", 1)[-1] in {"v", "is"}), None)
                    value = ""
                    if value_node is not None:
                        if value_node.tag.rsplit("}", 1)[-1] == "is":
                            value = "".join(node.text or "" for node in value_node.iter() if node.tag.rsplit("}", 1)[-1] == "t")
                        else:
                            value = value_node.text or ""
                            if kind == "s" and value.isdigit() and int(value) < len(shared):
                                value = shared[int(value)]
                    values.append(value)
                    if len(values) >= MAX_COLUMNS:
                        break
                rows.append(values)
                if len(rows) >= MAX_ROWS:
                    break
            tables.append({"name": f"Sheet {sheet_index}", "rows": rows})
    return {"kind": "spreadsheet", "tables": tables, "format": "XLSX"}


def _odf_preview(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        raw = _safe_zip_read(archive, "content.xml")
    return {"kind": "document", "content": _xml_text(raw)[:250_000], "format": path.suffix[1:].upper()}


def _epub_preview(path: Path) -> dict[str, Any]:
    parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = _safe_zip_names(archive, lambda name: name.lower().endswith((".xhtml", ".html", ".htm")), maximum=30)
        for name in names:
            parser = TextExtractor()
            parser.feed(_safe_zip_read(archive, name).decode("utf-8", errors="replace"))
            if parser.parts:
                parts.append("\n".join(parser.parts))
    return {"kind": "document", "content": "\n\n".join(parts)[:250_000], "format": "EPUB"}


def _eml_preview(path: Path) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes()[:MAX_STRUCTURED_BYTES])
    body = message.get_body(preferencelist=("plain",))
    content = body.get_content() if body else ""
    metadata = {
        "subject": str(message.get("subject", "")),
        "from": str(message.get("from", "")),
        "to": str(message.get("to", "")),
        "date": str(message.get("date", "")),
    }
    return {"kind": "email", "metadata": metadata, "content": str(content)[:200_000], "format": "EML"}


def _rtf_preview(path: Path) -> dict[str, Any]:
    text, truncated = _read_text(path)
    text = re.sub(r"\\'[0-9a-fA-F]{2}", "", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    return {"kind": "document", "content": text, "format": "RTF", "truncated": truncated}


def _archive_preview(path: Path) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist()[:MAX_ARCHIVE_ITEMS]:
                items.append({"name": info.filename, "size": info.file_size, "directory": info.is_dir()})
        return {"kind": "archive", "items": items, "format": "ZIP"}
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for info in archive.getmembers()[:MAX_ARCHIVE_ITEMS]:
                items.append({"name": info.name, "size": info.size, "directory": info.isdir()})
        return {"kind": "archive", "items": items, "format": "TAR"}
    return {"kind": "unsupported"}


def build_preview(path: Path, inline_url: str) -> dict[str, Any]:
    stat = path.stat()
    base: dict[str, Any] = {
        "name": path.name,
        "size": stat.st_size,
        "mime": guessed_mime(path),
        "extension": path.suffix.lower(),
    }
    direct = direct_preview_kind(path)
    if direct:
        return {**base, "kind": direct, "inline_url": inline_url}

    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            text, truncated = _read_text(path)
            parsed = json.loads(text)
            return {**base, "kind": "text", "content": json.dumps(parsed, indent=2, ensure_ascii=False), "truncated": truncated, "format": "JSON"}
        if suffix in {".csv", ".tsv"}:
            text, truncated = _read_text(path)
            dialect = csv.excel_tab if suffix == ".tsv" else csv.excel
            rows = []
            for row in csv.reader(io.StringIO(text), dialect=dialect):
                rows.append(row[:MAX_COLUMNS])
                if len(rows) >= MAX_ROWS:
                    break
            return {**base, "kind": "table", "rows": rows, "truncated": truncated or len(rows) >= MAX_ROWS, "format": suffix[1:].upper()}
        if suffix in TEXT_EXTENSIONS or base["mime"].startswith("text/") or suffix == ".svg":
            text, truncated = _read_text(path)
            return {**base, "kind": "text", "content": text, "truncated": truncated, "format": suffix[1:].upper() or "TEXT"}
        if suffix == ".docx" and stat.st_size <= MAX_STRUCTURED_BYTES:
            return {**base, **_docx_preview(path)}
        if suffix == ".xlsx" and stat.st_size <= MAX_STRUCTURED_BYTES:
            return {**base, **_xlsx_preview(path)}
        if suffix == ".pptx" and stat.st_size <= MAX_STRUCTURED_BYTES:
            return {**base, **_pptx_preview(path)}
        if suffix in {".odt", ".ods", ".odp"} and stat.st_size <= MAX_STRUCTURED_BYTES:
            return {**base, **_odf_preview(path)}
        if suffix == ".epub" and stat.st_size <= MAX_STRUCTURED_BYTES:
            return {**base, **_epub_preview(path)}
        if suffix == ".eml" and stat.st_size <= MAX_STRUCTURED_BYTES:
            return {**base, **_eml_preview(path)}
        if suffix == ".rtf":
            return {**base, **_rtf_preview(path)}
        if suffix in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"} and stat.st_size <= 200 * 1024 * 1024:
            return {**base, **_archive_preview(path)}
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile, tarfile.TarError, json.JSONDecodeError):
        return {**base, "kind": "unsupported", "error": "preview_failed"}
    return {**base, "kind": "unsupported"}
