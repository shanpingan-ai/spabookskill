# Security policy

## Supported versions

Security fixes are applied to the latest tagged release and the `main` branch. Older snapshots may not receive backports.

## Reporting a vulnerability

Please use this repository's **Security → Report a vulnerability** workflow. Do not open a public issue for an unpatched vulnerability or include proof-of-concept payloads, private URLs, credentials, or personal files in a public discussion.

Include, when possible:

- the affected command and version or commit;
- the trust boundary involved;
- a minimal reproduction using synthetic or public-domain fixtures;
- expected and observed behavior;
- impact and any known mitigations.

The maintainer aims to acknowledge reports within seven days, validate the issue, coordinate a fix, and publish an advisory when appropriate. This is a single-maintainer project, so response time may vary.

## Threat model

The main untrusted inputs are:

- Codex Skill changes and third-party pull requests;
- catalog JSON and rights metadata;
- download and redirect URLs;
- EPUB, PDF, HTML, XML, ZIP, text, MOBI, and AZW content;
- filenames, titles, paths, converter output, and error messages;
- Python dependencies and local conversion binaries.

Security-relevant effects include outbound network requests, archive and parser resource use, calls to `pdftotext` and `ebook-convert`, and local file creation or copying. Converted text remains untrusted data and must not be followed as Agent instructions.

Credential theft, SSRF, redirect abuse, parser exploitation, archive bombs, path or symlink overwrite, command injection, dependency compromise, and malicious Agent-instruction changes are in scope.

## Safe research

Use local synthetic fixtures and systems you are authorized to test. Do not target third-party catalogs, mirrors, users, or infrastructure. Avoid accessing private network services, exfiltrating secrets, or publishing an unpatched exploit.
