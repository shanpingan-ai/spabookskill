#!/usr/bin/env python3
"""Find explicitly open books and convert lawful ebook files to PDF + Markdown."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET


USER_AGENT = "find-open-books/1.0 (+rights-aware open book conversion)"
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024
SUPPORTED_SOURCES = ("gutenberg", "google-books")
FORMAT_PRIORITY = (
    "application/epub+zip",
    "application/pdf",
    "text/html; charset=utf-8",
    "text/html",
    "text/plain; charset=utf-8",
    "text/plain",
)


class PipelineError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    BLOCKS = {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl",
        "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4",
        "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
        "section", "table", "tr", "ul",
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg"}:
            self.ignored += 1
        elif not self.ignored and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg"} and self.ignored:
            self.ignored -= 1
        elif not self.ignored and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_text("".join(self.parts))


def http_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PipelineError(f"API request failed: {url}: {exc}") from exc


def clean_title(value: str) -> str:
    value = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", " ", value).strip()
    value = re.sub(r"\s+", " ", value)
    return value[:120] or "book"


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip() + "\n"


def unique_book_dir(base: Path, title: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    stem = clean_title(title)
    for index in range(1, 10_000):
        candidate = base / (stem if index == 1 else f"{stem} ({index})")
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise PipelineError(f"Could not create a collision-safe output directory under {base}")


def unique_output_stem(out_dir: Path, desired: str, existing_pdf: Path | None = None) -> str:
    stem = clean_title(desired)
    for index in range(1, 10_000):
        candidate = stem if index == 1 else f"{stem} ({index})"
        md_path = out_dir / f"{candidate}.md"
        pdf_path = out_dir / f"{candidate}.pdf"
        pdf_is_input = existing_pdf is not None and pdf_path.resolve() == existing_pdf.resolve()
        if not md_path.exists() and (not pdf_path.exists() or pdf_is_input):
            return candidate
    raise PipelineError(f"Could not choose collision-safe output names under {out_dir}")


def title_score(query: str, title: str) -> tuple[int, int]:
    q = re.sub(r"\W+", "", query, flags=re.UNICODE).casefold()
    t = re.sub(r"\W+", "", title, flags=re.UNICODE).casefold()
    if q == t:
        return (0, len(t))
    if t.startswith(q) or q.startswith(t):
        return (1, abs(len(t) - len(q)))
    if q in t or t in q:
        return (2, abs(len(t) - len(q)))
    return (3, abs(len(t) - len(q)))


def choose_gutenberg_format(formats: dict[str, str]) -> tuple[str, str] | None:
    normalized = {key.lower().replace("charset=", "charset="): value for key, value in formats.items()}
    for wanted in FORMAT_PRIORITY:
        for mime, url in normalized.items():
            compact = re.sub(r"\s+", "", mime)
            if compact == re.sub(r"\s+", "", wanted):
                return mime, url
    return None


def search_gutenberg(query: str, limit: int) -> list[dict[str, Any]]:
    url = "https://gutendex.com/books/?" + urllib.parse.urlencode({"search": query})
    data = http_json(url)
    results: list[dict[str, Any]] = []
    for item in data.get("results", []):
        if item.get("copyright") is not False:
            continue
        chosen = choose_gutenberg_format(item.get("formats") or {})
        if not chosen:
            continue
        mime, download_url = chosen
        authors = [person.get("name", "") for person in item.get("authors", []) if person.get("name")]
        results.append(
            {
                "source": "gutenberg",
                "id": str(item["id"]),
                "title": item.get("title") or f"Gutenberg {item['id']}",
                "authors": authors,
                "language": ", ".join(item.get("languages") or []),
                "rights": "Public domain (Gutendex copyright=false)",
                "mime": mime,
                "download_url": download_url,
            }
        )
        if len(results) >= limit:
            break
    return results


def google_record(item: dict[str, Any]) -> dict[str, Any] | None:
    info = item.get("volumeInfo") or {}
    access = item.get("accessInfo") or {}
    if access.get("publicDomain") is not True:
        return None
    if access.get("accessViewStatus") != "FULL_PUBLIC_DOMAIN":
        return None
    selected: tuple[str, str] | None = None
    for key, mime in (("epub", "application/epub+zip"), ("pdf", "application/pdf")):
        link = (access.get(key) or {}).get("downloadLink")
        if link:
            selected = (mime, link.replace("http://", "https://", 1))
            break
    if not selected:
        return None
    mime, download_url = selected
    return {
        "source": "google-books",
        "id": str(item["id"]),
        "title": info.get("title") or f"Google Books {item['id']}",
        "authors": info.get("authors") or [],
        "language": info.get("language") or "",
        "rights": "Public domain (Google Books FULL_PUBLIC_DOMAIN)",
        "country": access.get("country") or "",
        "mime": mime,
        "download_url": download_url,
    }


def search_google_books(query: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "q": f"intitle:{query}",
        "filter": "free-ebooks",
        "printType": "books",
        "projection": "full",
        "maxResults": min(max(limit * 2, 10), 40),
    }
    data = http_json("https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(params))
    results: list[dict[str, Any]] = []
    for item in data.get("items", []):
        record = google_record(item)
        if record:
            results.append(record)
        if len(results) >= limit:
            break
    return results


def search(query: str, limit: int, source: str) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    providers = []
    if source in {"all", "gutenberg"}:
        providers.append(("gutenberg", search_gutenberg))
    if source in {"all", "google-books"}:
        providers.append(("google-books", search_google_books))
    for name, provider in providers:
        try:
            results.extend(provider(query, limit))
        except PipelineError as exc:
            warnings.append(f"{name}: {exc}")
    results.sort(key=lambda item: (title_score(query, item["title"]), item["source"], item["id"]))
    return results[:limit], warnings


def fetch_record(source: str, identifier: str) -> dict[str, Any]:
    if source == "gutenberg":
        data = http_json(f"https://gutendex.com/books/{urllib.parse.quote(identifier)}/")
        if data.get("copyright") is not False:
            raise PipelineError("Refusing download: Gutendex does not mark this record copyright=false")
        chosen = choose_gutenberg_format(data.get("formats") or {})
        if not chosen:
            raise PipelineError("No supported downloadable format in the Gutendex record")
        mime, download_url = chosen
        return {
            "source": source,
            "id": str(data["id"]),
            "title": data.get("title") or f"Gutenberg {identifier}",
            "authors": [p.get("name", "") for p in data.get("authors", []) if p.get("name")],
            "language": ", ".join(data.get("languages") or []),
            "rights": "Public domain (Gutendex copyright=false)",
            "mime": mime,
            "download_url": download_url,
        }
    if source == "google-books":
        data = http_json(
            "https://www.googleapis.com/books/v1/volumes/" + urllib.parse.quote(identifier)
        )
        record = google_record(data)
        if not record:
            raise PipelineError(
                "Refusing download: Google Books does not expose this record as FULL_PUBLIC_DOMAIN "
                "with a downloadable file"
            )
        return record
    raise PipelineError(f"Unsupported source: {source}")


def extension_for(record: dict[str, Any], final_url: str, content_type: str) -> str:
    mime = (record.get("mime") or content_type or "").split(";", 1)[0].lower()
    mapping = {
        "application/epub+zip": ".epub",
        "application/pdf": ".pdf",
        "text/html": ".html",
        "text/plain": ".txt",
    }
    if mime in mapping:
        return mapping[mime]
    suffix = Path(urllib.parse.urlparse(final_url).path).suffix.lower()
    if suffix in {".epub", ".pdf", ".html", ".htm", ".txt"}:
        return suffix
    guessed = mimetypes.guess_extension(mime)
    return guessed or ".bin"


def download_record(record: dict[str, Any], out_dir: Path) -> tuple[Path, dict[str, Any]]:
    source_url = record.get("download_url") or ""
    parsed = urllib.parse.urlparse(source_url)
    if parsed.scheme not in {"https", "http"}:
        raise PipelineError("Refusing non-HTTP(S) download URL")
    if parsed.scheme == "http":
        source_url = urllib.parse.urlunparse(parsed._replace(scheme="https"))
    request = urllib.request.Request(source_url, headers={"User-Agent": USER_AGENT})
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    target: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
            suffix = extension_for(record, final_url, content_type)
            target = out_dir / f"{clean_title(record['title'])}{suffix}"
            with target.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise PipelineError("Download exceeds the 500 MB safety limit")
                    digest.update(chunk)
                    output.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if target:
            target.unlink(missing_ok=True)
        raise PipelineError(f"Download failed: {exc}") from exc
    except PipelineError:
        if target:
            target.unlink(missing_ok=True)
        raise
    if total == 0:
        target.unlink(missing_ok=True)
        raise PipelineError("Downloaded file is empty")
    provenance = {
        "title": record["title"],
        "authors": record.get("authors") or [],
        "catalog": record["source"],
        "catalog_id": record["id"],
        "rights": record["rights"],
        "country": record.get("country") or "",
        "source_url": source_url,
        "resolved_url": final_url,
        "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sha256": digest.hexdigest(),
        "bytes": total,
    }
    (out_dir / "source.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target, provenance


def decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def html_to_markdown(document: str) -> str:
    document = re.sub(r"^\s*<\?xml[^>]*\?>", "", document, count=1, flags=re.IGNORECASE)
    try:
        from bs4 import BeautifulSoup  # type: ignore
        from markdownify import markdownify  # type: ignore

        soup = BeautifulSoup(document, "html.parser")
        for node in soup(["script", "style", "svg", "nav"]):
            node.decompose()
        return normalize_text(markdownify(str(soup), heading_style="ATX"))
    except ImportError:
        parser = _TextExtractor()
        parser.feed(document)
        return parser.text()


def epub_spine_html(path: Path) -> list[tuple[str, str]]:
    chapters: list[tuple[str, str]] = []
    with zipfile.ZipFile(path) as archive:
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
        except (KeyError, ET.ParseError) as exc:
            raise PipelineError(f"Invalid EPUB container: {exc}") from exc
        rootfile = next((node for node in container.iter() if node.tag.endswith("rootfile")), None)
        if rootfile is None:
            raise PipelineError("Invalid EPUB: no rootfile")
        opf_name = rootfile.attrib.get("full-path")
        if not opf_name:
            raise PipelineError("Invalid EPUB: empty rootfile path")
        try:
            package = ET.fromstring(archive.read(opf_name))
        except (KeyError, ET.ParseError) as exc:
            raise PipelineError(f"Invalid EPUB package: {exc}") from exc
        manifest: dict[str, tuple[str, str]] = {}
        for node in package.iter():
            if node.tag.endswith("item") and node.attrib.get("id") and node.attrib.get("href"):
                manifest[node.attrib["id"]] = (
                    node.attrib["href"],
                    node.attrib.get("media-type", ""),
                )
        spine = [
            node.attrib.get("idref", "")
            for node in package.iter()
            if node.tag.endswith("itemref")
        ]
        base = PurePosixPath(opf_name).parent
        for idref in spine:
            item = manifest.get(idref)
            if not item:
                continue
            href, media_type = item
            if media_type not in {"application/xhtml+xml", "text/html"}:
                continue
            chapter_name = str(base / urllib.parse.unquote(href))
            try:
                document = decode_bytes(archive.read(chapter_name))
            except KeyError:
                continue
            chapters.append((chapter_name, document))
    if not chapters:
        raise PipelineError("EPUB contains no readable spine chapters")
    return chapters


def file_to_markdown(path: Path) -> tuple[str, list[str]]:
    suffix = path.suffix.lower()
    warnings: list[str] = []
    if suffix in {".txt", ".md", ".markdown"}:
        return normalize_text(decode_bytes(path.read_bytes())), warnings
    if suffix in {".html", ".htm", ".xhtml"}:
        return html_to_markdown(decode_bytes(path.read_bytes())), warnings
    if suffix == ".epub":
        sections = []
        for chapter_name, document in epub_spine_html(path):
            converted = html_to_markdown(document).strip()
            if converted:
                sections.append(converted)
        return normalize_text("\n\n---\n\n".join(sections)), warnings
    if suffix == ".pdf":
        tool = shutil.which("pdftotext")
        if not tool:
            raise PipelineError("PDF-to-Markdown requires pdftotext (Poppler)")
        with tempfile.TemporaryDirectory(prefix="open-book-") as temp_dir:
            text_path = Path(temp_dir) / "book.txt"
            result = subprocess.run(
                [tool, "-layout", str(path), str(text_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise PipelineError(f"pdftotext failed: {result.stderr.strip()}")
            text = decode_bytes(text_path.read_bytes())
        warnings.append("PDF layout was flattened to text; scanned pages may require OCR")
        return normalize_text(text), warnings
    if suffix in {".mobi", ".azw", ".azw3"}:
        tool = shutil.which("ebook-convert")
        if not tool:
            raise PipelineError("MOBI/AZW conversion requires Calibre's ebook-convert")
        with tempfile.TemporaryDirectory(prefix="open-book-") as temp_dir:
            epub_path = Path(temp_dir) / "book.epub"
            result = subprocess.run(
                [tool, str(path), str(epub_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise PipelineError(f"ebook-convert failed: {result.stderr.strip()}")
            return file_to_markdown(epub_path)
    raise PipelineError(f"Unsupported input format: {suffix or '(none)'}")


def markdown_to_pdf(markdown: str, output: Path, title: str) -> None:
    try:
        from reportlab.lib.enums import TA_CENTER  # type: ignore
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
        from reportlab.lib.units import mm  # type: ignore
        from reportlab.pdfbase import pdfmetrics  # type: ignore
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer  # type: ignore
    except ImportError as exc:
        raise PipelineError("Markdown-to-PDF requires the Python package reportlab") from exc

    font_name = "STSong-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    except Exception:
        font_name = "Helvetica"

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "BookBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=16,
        spaceAfter=5,
        wordWrap="CJK",
    )
    heading_styles = {
        1: ParagraphStyle("BookH1", parent=body, fontSize=20, leading=26, spaceBefore=12, spaceAfter=10),
        2: ParagraphStyle("BookH2", parent=body, fontSize=16, leading=21, spaceBefore=10, spaceAfter=8),
        3: ParagraphStyle("BookH3", parent=body, fontSize=13, leading=18, spaceBefore=8, spaceAfter=6),
    }
    title_style = ParagraphStyle(
        "BookTitle",
        parent=heading_styles[1],
        alignment=TA_CENTER,
        spaceAfter=18,
    )
    bullet_style = ParagraphStyle("BookBullet", parent=body, leftIndent=12, firstLineIndent=-8)

    story: list[Any] = [Paragraph(html.escape(title), title_style)]
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 3))
            continue
        if line == "---":
            story.append(PageBreak())
            continue
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            level = min(len(match.group(1)), 3)
            story.append(Paragraph(html.escape(match.group(2)), heading_styles[level]))
            continue
        if re.match(r"^[-*+]\s+", line):
            text = re.sub(r"^[-*+]\s+", "", line)
            story.append(Paragraph("• " + html.escape(text), bullet_style))
            continue
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"(\*\*|__|\*|_)(.*?)\1", r"\2", line)
        story.append(Paragraph(html.escape(line), body))

    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    document.build(story)


def convert_file(path: Path, out_dir: Path, title: str | None = None) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise PipelineError(f"Input file does not exist: {path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    book_title = title or path.stem
    existing_pdf = path if path.suffix.lower() == ".pdf" else None
    stem = unique_output_stem(out_dir, book_title, existing_pdf)
    markdown, warnings = file_to_markdown(path)
    md_path = out_dir / f"{stem}.md"
    pdf_path = out_dir / f"{stem}.pdf"
    md_path.write_text(markdown, encoding="utf-8")
    if path.suffix.lower() == ".pdf":
        if path != pdf_path:
            shutil.copy2(path, pdf_path)
    else:
        markdown_to_pdf(markdown, pdf_path, book_title)
    if not md_path.stat().st_size or not pdf_path.stat().st_size:
        raise PipelineError("Conversion produced an empty output")
    return {
        "input": str(path),
        "markdown": str(md_path.resolve()),
        "pdf": str(pdf_path.resolve()),
        "warnings": warnings,
    }


def print_results(results: list[dict[str, Any]], warnings: list[str]) -> None:
    for index, item in enumerate(results, 1):
        authors = "; ".join(item.get("authors") or []) or "Unknown author"
        detail = f"{item['source']}:{item['id']} · {item['mime']} · {item['rights']}"
        if item.get("country"):
            detail += f" · country={item['country']}"
        print(f"[{index}] {item['title']}\n    {authors}\n    {detail}")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search explicit public-domain catalogs and convert lawful ebooks to PDF + Markdown."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search supported open-book catalogs")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=8)
    search_parser.add_argument("--source", choices=("all",) + SUPPORTED_SOURCES, default="all")
    search_parser.add_argument("--json", action="store_true")

    run_parser = subparsers.add_parser("run", help="Search, download, and convert a result")
    run_parser.add_argument("query")
    run_parser.add_argument("--pick", type=int, default=1, help="1-based result number")
    run_parser.add_argument("--limit", type=int, default=8)
    run_parser.add_argument("--source", choices=("all",) + SUPPORTED_SOURCES, default="all")
    run_parser.add_argument("--out-dir", type=Path, default=Path.cwd() / "books")

    fetch_parser = subparsers.add_parser("fetch", help="Download and convert a known catalog record")
    fetch_parser.add_argument("source", choices=SUPPORTED_SOURCES)
    fetch_parser.add_argument("identifier")
    fetch_parser.add_argument("--out-dir", type=Path, default=Path.cwd() / "books")

    convert_parser = subparsers.add_parser("convert", help="Convert a lawful local ebook")
    convert_parser.add_argument("path", type=Path)
    convert_parser.add_argument("--out-dir", type=Path, default=Path.cwd() / "converted")
    convert_parser.add_argument("--title")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "search":
            if args.limit < 1 or args.limit > 40:
                raise PipelineError("--limit must be between 1 and 40")
            results, warnings = search(args.query, args.limit, args.source)
            if args.json:
                print(json.dumps({"results": results, "warnings": warnings}, ensure_ascii=False, indent=2))
            else:
                print_results(results, warnings)
            return 0 if results else 2

        if args.command == "convert":
            result = convert_file(args.path, args.out_dir.resolve(), args.title)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "run":
            if args.limit < 1 or args.limit > 40:
                raise PipelineError("--limit must be between 1 and 40")
            results, warnings = search(args.query, args.limit, args.source)
            for warning in warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
            if not results:
                raise PipelineError("No explicitly public-domain downloadable result found")
            if args.pick < 1 or args.pick > len(results):
                raise PipelineError(f"--pick must be between 1 and {len(results)}")
            record = fetch_record(results[args.pick - 1]["source"], results[args.pick - 1]["id"])
        else:
            record = fetch_record(args.source, args.identifier)

        book_dir = unique_book_dir(args.out_dir.resolve(), record["title"])
        original, provenance = download_record(record, book_dir)
        converted = convert_file(original, book_dir, record["title"])
        print(
            json.dumps(
                {
                    "record": record,
                    "original": str(original.resolve()),
                    "provenance": str((book_dir / "source.json").resolve()),
                    "sha256": provenance["sha256"],
                    **converted,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
