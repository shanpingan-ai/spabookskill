from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "open_book.py"
SPEC = importlib.util.spec_from_file_location("open_book", MODULE_PATH)
assert SPEC and SPEC.loader
open_book = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(open_book)


def test_clean_title_removes_path_and_control_characters() -> None:
    assert open_book.clean_title("../bad\\name:\x00book") == "bad name book"
    assert open_book.clean_title("..") == "book"


def test_google_record_requires_explicit_public_domain_signal() -> None:
    base = {
        "id": "volume",
        "volumeInfo": {"title": "Example"},
        "accessInfo": {
            "publicDomain": True,
            "accessViewStatus": "FULL_PUBLIC_DOMAIN",
            "epub": {"downloadLink": "https://books.googleusercontent.com/book.epub"},
        },
    }
    assert open_book.google_record(base) is not None
    base["accessInfo"]["publicDomain"] = False
    assert open_book.google_record(base) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://www.gutenberg.org/book.epub",
        "https://user:pass@www.gutenberg.org/book.epub",
        "https://www.gutenberg.org:8443/book.epub",
        "https://gutenberg.org.evil.example/book.epub",
        "https://127.0.0.1/book.epub",
    ],
)
def test_url_policy_rejects_unsafe_destinations(url: str) -> None:
    with pytest.raises(open_book.PipelineError):
        open_book.validate_https_url(
            url,
            open_book.DOWNLOAD_ALLOWED_DOMAINS["gutenberg"],
        )


def test_url_policy_accepts_allowed_subdomain() -> None:
    assert open_book.validate_https_url(
        "https://www.gutenberg.org/cache/book.epub",
        open_book.DOWNLOAD_ALLOWED_DOMAINS["gutenberg"],
    ).startswith("https://www.gutenberg.org/")


def test_archive_rejects_parent_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.epub"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.xhtml", "bad")
    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(open_book.PipelineError, match="unsafe path"):
            open_book.validate_zip_archive(archive)


def test_archive_rejects_suspicious_compression_ratio(tmp_path: Path) -> None:
    archive_path = tmp_path / "bomb.epub"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.xhtml", b"0" * (2 * 1024 * 1024))
    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(open_book.PipelineError, match="compression ratio"):
            open_book.validate_zip_archive(archive)


def make_epub(path: Path) -> None:
    container = """<?xml version="1.0"?>
    <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles><rootfile full-path="OPS/package.opf"/></rootfiles>
    </container>"""
    package = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf">
      <manifest>
        <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine><itemref idref="chapter"/></spine>
    </package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OPS/package.opf", package)
        archive.writestr(
            "OPS/chapter.xhtml", "<html><body><h1>Chapter</h1><p>Hello.</p></body></html>"
        )


def test_valid_epub_signature_and_spine(tmp_path: Path) -> None:
    epub = tmp_path / "book.epub"
    make_epub(epub)
    open_book.validate_downloaded_file(epub, "application/epub+zip")
    chapters = open_book.epub_spine_html(epub)
    assert chapters == [
        ("OPS/chapter.xhtml", "<html><body><h1>Chapter</h1><p>Hello.</p></body></html>")
    ]


def test_html_conversion_discards_active_content() -> None:
    converted = open_book.html_to_markdown(
        "<html><body><p>Keep me</p><script>stealSecrets()</script></body></html>"
    )
    assert "Keep me" in converted
    assert "stealSecrets" not in converted


def test_text_input_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "large.txt"
    source.write_bytes(b"1234")
    monkeypatch.setattr(open_book, "MAX_TEXT_INPUT_BYTES", 3)
    with pytest.raises(open_book.PipelineError, match="Text input"):
        open_book.file_to_markdown(source)


def test_local_input_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "large.epub"
    source.write_bytes(b"1234")
    monkeypatch.setattr(open_book, "MAX_LOCAL_INPUT_BYTES", 3)
    with pytest.raises(open_book.PipelineError, match="Input file"):
        open_book.convert_file(source, tmp_path / "out")


def test_atomic_write_refuses_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "result.md"
    destination.write_text("original", encoding="utf-8")
    with pytest.raises(open_book.PipelineError, match="overwrite"):
        open_book.atomic_write_text(destination, "replacement")
    assert destination.read_text(encoding="utf-8") == "original"


def test_download_record_rejects_ip_literal_before_network(tmp_path: Path) -> None:
    record = {
        "source": "gutenberg",
        "id": "1",
        "title": "Unsafe",
        "rights": "Public domain",
        "mime": "application/epub+zip",
        "download_url": "https://127.0.0.1/book.epub",
    }
    with pytest.raises(open_book.PipelineError, match="allowlist"):
        open_book.download_record(record, tmp_path)
