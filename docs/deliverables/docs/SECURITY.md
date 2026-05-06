# CODI Security Guide

CODI is built for environments with strict security and compliance requirements. This guide summarises safeguards, configuration options, and operational recommendations.

## 1. Security Model

1. **Rules-first rendering** – Only vetted templates generate Dockerfiles; LLM output cannot introduce arbitrary instructions.
2. **Air-gap enforcement** – Outbound HTTP(S) requests are blocked by default via `core.security.enforce_airgap_guard`.
3. **Non-root containers** – Both Slim and Complete images run as user `codi` (UID/GID 1000).
4. **Deterministic artefacts** – Every optimisation persists inputs, outputs, metrics, and environment metadata for auditing.
5. **Policy allowlists** – `patterns/rules.yml` enumerates instructions that require explicit rationale (e.g., `curl`, package managers).

## 2. Air-Gap Controls

- `AIRGAP=true` (default) blocks outgoing HTTP calls using `httpx` wrappers.
- `AIRGAP_ALLOWLIST="host1,host2"` permits specific hosts (comma-separated). Wildcards are not supported; specify exact hostnames.
- CLI/API commands and LLM requests respect the guard. Attempting to reach unapproved hosts raises `SecurityPolicyError`.

### Testing Air-Gap Configuration

```bash
AIRGAP_ALLOWLIST="testserver" python -m pytest tests/test_security.py
```

## 3. Container Hardening

| Control | Description |
| --- | --- |
| Non-root user | Dockerfiles create `codi` user and switch away from root before running application code. |
| Minimal packages | Slim image installs only runtime dependencies; Complete image adds compiler toolchain solely for llama.cpp build stage. |
| `/work` volume | Host project mounted explicitly, preventing accidental context leakage. |
| Health checks | Containers expose `/healthz` endpoints to integrate with orchestrators. |

## 4. Template Safeguards

- Templates include rationale comments describing risky instructions.
- Policy notes appear in reports to highlight non-standard operations.
- CMD rewrites convert shell-form instructions to exec-form, reducing injection and signal-handling issues.

## 5. LLM Safety

- LLM responses are parsed and validated; any suggestion containing Dockerfile syntax outside allowed placeholders is rejected.
- Adapter metadata includes version and checksum to ensure provenance.
- Complete container never downloads models at runtime—weights must be mounted explicitly.

## 6. Secrets Handling

- CODI does not request credentials; any secrets in Dockerfiles remain local to the run directory.
- `.dockerignore` excludes sensitive files from container builds.
- When collecting data via GitHub, use dedicated tokens stored outside the repository (e.g., env var `GITHUB_TOKEN`).

## 7. Compliance Artifacts

- Reports include environment snapshots for traceability.
- Release workflow generates SBOMs (SPDX JSON) and attaches them as signed attestations.
- cosign keyless signing proves provenance of published images.

## 8. Operational Recommendations

| Area | Guidance |
| --- | --- |
| Network | Run containers within private subnets; expose ports via ingress with TLS termination. |
| Logging | Forward logs to central system; redact project paths if needed. |
| Storage | Store `runs/` on encrypted volumes; set retention policies. |
| Access control | Restrict who can run Complete container with adapters to prevent unauthorised model use. |
| Policy review | Regularly audit `patterns/rules.yml` allowlists and CMD rewrites. |

## 9. Incident Response

1. Identify problematic run using timestamped directory.
2. Review `report.md`, `metrics.json`, and `environment.json` for context.
3. Check `docker logs` (containers) or CLI output for security warnings.
4. If LLM involved, inspect `llm_metrics.json` to confirm adapter and ranking details.
5. Reproduce issue in isolated environment before applying fixes.

## 10. Testing Security Controls

- `tests/test_security.py` validates air-gap enforcement, adapter path checks, and allowlists.
- Use `make llm-runtime-test` to ensure Complete container handles adapter failures gracefully.

## Related Documentation

- [OPERATIONS.md](./OPERATIONS.md) for day-2 practices that depend on security controls.
- [CICD_RELEASE.md](./CICD_RELEASE.md) for provenance, signing, and SBOM details.
- [RULES_GUIDE.md](./RULES_GUIDE.md) for policy allowlists enforced during rendering.
- [LLM_MODULE.md](./LLM_MODULE.md) for adapter validation and runtime safeguards.
