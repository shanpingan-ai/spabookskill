# Rights and source rules

## Supported network catalogs

### Project Gutenberg through Gutendex

Allow a download only when the record's `copyright` field is exactly `false`. Prefer EPUB, then PDF, UTF-8 HTML, and UTF-8 plain text. The check applies to the catalog record and its linked Project Gutenberg files.

### Google Books

Allow a download only when all of these are true:

- `accessInfo.publicDomain` is exactly `true`;
- `accessInfo.accessViewStatus` is `FULL_PUBLIC_DOMAIN`;
- `accessInfo.epub.downloadLink` or `accessInfo.pdf.downloadLink` exists.

Availability and public-domain status are country-dependent. Do not reuse a decision made for a different country or account context.

## Metadata-only and unsupported sources

Open Library and library catalogs may help identify a title or edition, but a catalog record is not permission to download the text.

Internet Archive states that it does not guarantee the copyright status of uploaded items. Do not automate an item unless a future implementation verifies a reliable license signal and excludes loans, restricted items, and ambiguous uploads.

Do not download from Z-Library, Anna's Archive, WeLib, KGBook, their mirrors, URL shorteners, or similar shadow-library indexes. Do not use them as fallback search providers.

## Rights decision

Use this order:

1. Accept a supported catalog's explicit machine-readable public-domain signal.
2. Accept an explicit, compatible Creative Commons license only when the exact file/edition is covered and attribution requirements can be preserved.
3. Process a local file when the user states or reasonably indicates lawful possession or permission.
4. Otherwise stop at metadata and offer legal acquisition options.

Never determine rights solely from publication year, author death date, search snippets, file names, or the fact that a file is technically reachable.

## Conversion boundaries

Conversion changes format, not rights. Do not remove DRM, passwords, watermarks used as access controls, lending limits, or account restrictions. Preserve source and license metadata alongside outputs.
