# Security & Air-Gap Verification

This document covers the security gates and air-gap enforcement validation suite. The suite exercises synchronous and asynchronous network guards, policy validation, and end-to-end rejection paths.

## How to Run

```bash
python3 -m pytest tests/test_security.py
```

## Coverage

- **Dockerfile policy gates** — `validate_or_raise` rejects disallowed base images, URL-based `ADD`, `sudo`, and `--privileged` runs.
- **Air-gap enforcement (sync & async)** — `enforce_airgap_guard` blocks outbound HTTP(S) requests for module-level helpers, `httpx.Client`, and `httpx.AsyncClient` when `AIRGAP=true`.
- **Allowlist sanity** — loopback targets and host allowlist entries bypass the guard while other destinations raise `AirgapViolation`.
- **Model mount protections** — verifies mount path resolution and opt-in directory creation.
- **BuildRunner integration** — an intentionally unsafe project is refused with a user-facing `BuildRunnerError`, demonstrating that CLI/API flows surface security failures.

## Results

- **Command output:**

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0
collected 8 items

tests/test_security.py ........                                          [100%]

============================== 8 passed in 0.14s ===============================
```

- **Status:** ✅ All security verification scenarios passed on 2025-10-31.
- **Artefacts:** Security guard behaviour is exercised entirely via unit tests; no additional run artefacts are produced beyond the standard pytest report.
