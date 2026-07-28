from __future__ import annotations

import json
import zipfile
from pathlib import Path

from oniondrop.preview import build_preview


def write_zip(path: Path, members: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def test_text_json_csv_and_archive_previews(tmp_path: Path) -> None:
    text = tmp_path / "note.md"
    text.write_text("# Private note", encoding="utf-8")
    assert build_preview(text, "/inline")["kind"] == "text"

    data = tmp_path / "data.json"
    data.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    preview = build_preview(data, "/inline")
    assert preview["format"] == "JSON"
    assert '"hello": "world"' in preview["content"]

    table = tmp_path / "table.csv"
    table.write_text("name,value\nOnionDrop,2\n", encoding="utf-8")
    assert build_preview(table, "/inline")["rows"][1] == ["OnionDrop", "2"]

    archive = tmp_path / "bundle.zip"
    write_zip(archive, {"a.txt": "a", "folder/b.txt": "b"})
    result = build_preview(archive, "/inline")
    assert result["kind"] == "archive"
    assert {item["name"] for item in result["items"]} == {"a.txt", "folder/b.txt"}


def test_office_and_epub_previews(tmp_path: Path) -> None:
    docx = tmp_path / "sample.docx"
    write_zip(docx, {"word/document.xml": '<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body></w:document>'})
    assert "Hello DOCX" in build_preview(docx, "/inline")["content"]

    xlsx = tmp_path / "sample.xlsx"
    write_zip(
        xlsx,
        {
            "xl/sharedStrings.xml": '<sst xmlns="x"><si><t>Name</t></si><si><t>OnionDrop</t></si></sst>',
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="x"><sheetData><row><c t="s"><v>0</v></c></row><row><c t="s"><v>1</v></c></row></sheetData></worksheet>',
        },
    )
    result = build_preview(xlsx, "/inline")
    assert result["kind"] == "spreadsheet"
    assert result["tables"][0]["rows"] == [["Name"], ["OnionDrop"]]

    pptx = tmp_path / "sample.pptx"
    write_zip(pptx, {"ppt/slides/slide1.xml": '<p:sld xmlns:p="p" xmlns:a="a"><a:t>Hello slide</a:t></p:sld>'})
    assert "Hello slide" in build_preview(pptx, "/inline")["content"]

    odt = tmp_path / "sample.odt"
    write_zip(odt, {"content.xml": '<office:document xmlns:office="o" xmlns:text="t"><text:p>Hello ODT</text:p></office:document>'})
    assert "Hello ODT" in build_preview(odt, "/inline")["content"]

    epub = tmp_path / "book.epub"
    write_zip(epub, {"chapter.xhtml": "<html><body><h1>Chapter</h1><p>Private reading</p></body></html>"})
    assert "Private reading" in build_preview(epub, "/inline")["content"]


def test_oversized_zip_member_is_rejected_without_expansion(tmp_path: Path) -> None:
    docx = tmp_path / "bomb.docx"
    write_zip(docx, {"word/document.xml": b"x" * (8 * 1024 * 1024 + 1)})
    result = build_preview(docx, "/inline")
    assert result["kind"] == "unsupported"
    assert result["error"] == "preview_failed"


def test_direct_preview_types(tmp_path: Path) -> None:
    for filename, kind in [("photo.png", "image"), ("paper.pdf", "pdf"), ("audio.mp3", "audio"), ("clip.mp4", "video")]:
        path = tmp_path / filename
        path.write_bytes(b"placeholder")
        result = build_preview(path, "/api/file")
        assert result["kind"] == kind
        assert result["inline_url"] == "/api/file"
