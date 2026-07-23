---
name: find-open-books
description: Search for books by title in legitimate open-book catalogs, download only files explicitly marked public-domain or openly licensed, and convert legally obtained EPUB, PDF, HTML, or text files to both PDF and Markdown. Use when a user asks to find, download, archive, or convert a public-domain/open-license book, or to convert an ebook file they already lawfully possess. Do not use this skill to obtain copyrighted books from shadow libraries or to bypass payments, accounts, DRM, lending limits, or access controls.
---

# Find Open Books

Use the bundled command-line program for deterministic searching, downloading, provenance recording, and conversion:

```bash
python3 scripts/open_book.py --help
```

## Apply the rights gate

Download a network result only when the supported catalog explicitly reports it as public domain or supplies an accepted open-license URL. Treat missing, ambiguous, user-written, or conflicting rights metadata as not downloadable.

Never automate Z-Library, Anna's Archive, WeLib, KGBook, mirrors, link shorteners, torrents, DRM removal, login bypasses, borrowed-item extraction, or other access-control circumvention. Do not infer that an old title makes a particular edition public domain.

Local files may be converted after the user states or reasonably indicates they own the file or have permission to process it. Conversion does not remove DRM.

Read [references/legal-sources.md](references/legal-sources.md) when a source is unclear, a result lacks a license, or the user asks why a download was refused.

## Search before downloading

Search supported legal catalogs:

```bash
python3 scripts/open_book.py search "Pride and Prejudice" --limit 8
```

Return the numbered results with title, author, source, format, and rights status. Ask the user to choose when several editions are plausible. It is acceptable to choose the top exact-title match when the user asked for an automatic best match.

## Download and convert

Run the complete pipeline for the best result:

```bash
python3 scripts/open_book.py run "Pride and Prejudice" --out-dir ./books
```

Choose a particular search result:

```bash
python3 scripts/open_book.py run "Pride and Prejudice" --pick 2 --out-dir ./books
```

Or fetch a known supported catalog record:

```bash
python3 scripts/open_book.py fetch gutenberg 1342 --out-dir ./books
python3 scripts/open_book.py fetch google-books VOLUME_ID --out-dir ./books
```

The command creates a collision-safe subfolder inside the output directory. That book folder contains:

- the original downloaded file;
- a Markdown conversion;
- a PDF conversion;
- `source.json` with catalog, source URL, rights signal, timestamp, and SHA-256.

Preserve `source.json`. Report conversion warnings, especially OCR or layout loss.

## Convert a lawful local file

```bash
python3 scripts/open_book.py convert /absolute/path/to/book.epub --out-dir ./converted
```

Supported inputs:

- EPUB, HTML, and TXT: convert internally;
- PDF: preserve the PDF and extract Markdown with `pdftotext`;
- MOBI/AZW3: require Calibre's `ebook-convert`;
- scanned PDFs: run OCR separately only when the user requests it and has processing rights.

Do not claim visual fidelity for Markdown. Tables, footnotes, multi-column pages, ruby text, and scanned pages may need manual cleanup.

## Verify the result

Confirm that both `.pdf` and `.md` exist and are non-empty. Open or sample the Markdown and inspect the PDF page count when tools are available. Include the output paths and provenance path in the final response.
