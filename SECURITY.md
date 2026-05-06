# Security Policy

## Reporting a vulnerability

Do not open a public GitHub issue for security vulnerabilities.

Report privately via **GitHub Security Advisories**:
`https://github.com/KiniunCorp/codi/security/advisories/new`

Include in your report:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Output of `codi --version`
- Relevant logs or error output

**Response SLA:**
- Acknowledgement within **5 business days**
- Initial assessment within **10 business days**
- Fix or mitigation communicated within **30 days** for confirmed vulnerabilities

## Supported versions

| Version | Supported |
|---------|-----------|
| latest (0.1.x) | ✅ |
| older | ❌ |

## Scope

The following surfaces are in scope for security reports:

- **Air-gap enforcement** — `core/security.py` outbound HTTP(S) interceptor; bypass or circumvention of `AIRGAP=true` defaults.
- **Dockerfile policy gates** — `core/security.py` pattern checks (`ADD http://`, `--privileged`, `sudo`, base-image allowlists); unexpected acceptance of disallowed patterns.
- **Template rendering boundary** — `core/llm.py` token validator ensuring the LLM layer cannot emit raw Dockerfile instructions outside template placeholders.
- **Adapter integrity** — `docker/scripts/verify_adapter.py` checksum verification; loading of tampered or unsigned adapters.
- **Container runtime** — privilege escalation, unintended outbound network access, or secrets exposure in `codi:slim` or `codi:complete` images.

Out of scope: vulnerabilities in third-party dependencies should be reported to their maintainers directly.
