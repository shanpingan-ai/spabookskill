# find-open-books

[![CI](https://github.com/shanpingan-ai/spabookskill/actions/workflows/ci.yml/badge.svg)](https://github.com/shanpingan-ai/spabookskill/actions/workflows/ci.yml)
[![CodeQL](https://github.com/shanpingan-ai/spabookskill/actions/workflows/codeql.yml/badge.svg)](https://github.com/shanpingan-ai/spabookskill/actions/workflows/codeql.yml)

`find-open-books` is a rights-aware Codex Skill and deterministic Python CLI for finding explicitly public-domain books and converting lawfully obtained ebooks to PDF and Markdown.

It is designed to keep Agent automation inside an auditable boundary: supported catalogs must supply an explicit rights signal, network destinations are allowlisted, downloaded content is treated as untrusted, and every network result receives a provenance record.

## What it does

- searches Gutendex and Google Books;
- downloads only records explicitly marked public domain by a supported catalog;
- refuses shadow libraries, DRM removal, account bypasses, torrents, and ambiguous rights metadata;
- converts EPUB, PDF, HTML, TXT, Markdown, MOBI, AZW, and AZW3 inputs;
- writes both PDF and Markdown outputs;
- records catalog ID, source and resolved URLs, rights signal, timestamp, byte count, and SHA-256 in `source.json`;
- restricts outbound hosts and redirects, limits download and EPUB expansion size, and times out external converters.

Public-domain status can vary by edition and jurisdiction. The catalog signal and provenance file support review; they are not legal advice.

## Repository layout

```text
SKILL.md                    Codex Skill instructions and safety policy
agents/openai.yaml          Agent metadata
scripts/open_book.py        Search, download, provenance, and conversion CLI
references/legal-sources.md Rights-source policy
tests/                      Offline regression and security-boundary tests
```

## Requirements

- Python 3.10 or newer;
- Python packages in `requirements.txt`;
- Poppler's `pdftotext` for PDF-to-Markdown conversion;
- Calibre's `ebook-convert` for MOBI/AZW/AZW3 conversion.

Install the Python dependencies in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Usage

Search without downloading:

```bash
python3 scripts/open_book.py search "Pride and Prejudice" --limit 8
```

Download and convert the best exact-title result:

```bash
python3 scripts/open_book.py run "Pride and Prejudice" --out-dir ./books
```

Fetch a known supported record:

```bash
python3 scripts/open_book.py fetch gutenberg 1342 --out-dir ./books
python3 scripts/open_book.py fetch google-books VOLUME_ID --out-dir ./books
```

Convert a local file that you own or are authorized to process:

```bash
python3 scripts/open_book.py convert /absolute/path/to/book.epub --out-dir ./converted
```

Each downloaded book is placed in a collision-safe directory containing the original file, converted PDF and Markdown, and `source.json`.

## Security model

Catalog responses, redirect targets, downloaded files, book text, conversion logs, and generated Markdown are untrusted input. They must never be interpreted as Agent instructions.

The CLI currently enforces:

- HTTPS-only, source-specific domain allowlists for APIs, downloads, and redirects;
- rejection of embedded URL credentials, IP-literal URLs, and non-standard ports;
- a 500 MB network download limit;
- EPUB entry-count, path, encryption, expanded-size, per-entry, and compression-ratio checks;
- bounded XML and chapter reads;
- hardened XML parsing through `defusedxml`;
- bounded local inputs and converter outputs;
- PDF and EPUB signature checks;
- five-minute timeouts for `pdftotext` and `ebook-convert`;
- collision-safe output naming and no-overwrite publication;
- SHA-256 and explicit untrusted-content metadata in provenance records.

See [SECURITY.md](SECURITY.md) for reporting and scope.

## Development

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m py_compile scripts/open_book.py
ruff check .
ruff format --check .
pytest
```

Tests are offline and use generated fixtures; they do not download books.

## Contributing

Contributions are welcome. Changes to `SKILL.md`, network allowlists, parser limits, subprocess behavior, dependencies, or output paths are security-sensitive and require focused tests and maintainer review. See [CONTRIBUTING.md](CONTRIBUTING.md).

## 中文简介

`find-open-books` 是一个具备版权来源门槛和溯源记录的 Codex Skill 与 Python CLI。它只从支持的合法目录下载被明确标记为公共领域的版本，并将依法获得的电子书转换为 PDF 和 Markdown。下载内容始终被视为不可信数据，不能作为 Agent 指令执行。
