# Contributing

Thank you for helping improve `find-open-books`.

## Before opening a pull request

1. Open an issue for a substantial behavioral change or new catalog integration.
2. Keep the change narrowly scoped.
3. Add or update offline tests using synthetic or explicitly public-domain fixtures.
4. Run the full local verification commands.
5. Explain any change to trust boundaries, network destinations, parser limits, subprocesses, dependencies, or filesystem behavior.

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m py_compile scripts/open_book.py
ruff check .
ruff format --check .
pytest
```

## Rights requirements

New network sources must expose a machine-readable public-domain or accepted open-license signal for the exact downloadable record. A free preview, readable webpage, old publication date, user assertion, or missing copyright field is not sufficient.

Do not add shadow libraries, torrents, link shorteners, login automation, DRM removal, lending extraction, or payment/access-control bypasses.

## Security-sensitive changes

The following require explicit maintainer review and focused regression tests:

- `SKILL.md` or Agent metadata;
- API/download domain allowlists and redirect handling;
- archive, XML, HTML, PDF, or ebook parsing;
- output paths, file publication, deletion, or copying;
- subprocess commands and timeouts;
- dependency additions or upgrades;
- provenance and rights decisions.

Treat all catalog data and book content as untrusted. Tests must not depend on live third-party services and must not contain credentials or copyrighted book files.

## Pull request checklist

- [ ] The change has tests.
- [ ] CI and local checks pass.
- [ ] Rights behavior remains fail-closed.
- [ ] Untrusted content is never promoted to Agent instructions.
- [ ] Network, file, and subprocess effects are documented.
- [ ] No secrets, personal files, or unnecessary binary fixtures are included.
