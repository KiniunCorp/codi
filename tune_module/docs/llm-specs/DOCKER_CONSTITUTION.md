# DOCKER OPTIMIZATION CONSTITUTION
*Strict rules for generating "Golden" Dockerfiles.*

## I. SECURITY PROTOCOL (CIS v1.6.0)
1.  **Non-Root:** Container MUST switch to a non-root user (UID > 1000) at the end.
2.  **Pinned Tags:** NEVER use `:latest`. Use explicit versions (e.g., `node:18-alpine`).
3.  **No Secrets:** NEVER use `ENV` for passwords/keys. Use `ARG` or runtime mounts.
4.  **Minimal Base:** Prefer `alpine`, `slim`, or `distroless`.

## II. PERFORMANCE (BuildKit)
1.  **Multi-Stage:** STRICTLY required for compiled languages. Separate build tools from runtime artifacts.
2.  **Cache Ordering:** `COPY package.json` -> `RUN install` -> `COPY . .`.
3.  **Package Managers:**
    * **Apt:** `apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*`.
    * **Apk:** `apk add --no-cache ...`.
4.  **Cache Mounts:** Use `RUN --mount=type=cache...` for `npm/pip/maven`.

## III. SYNTAX (Hadolint)
* **DL3003:** Do not use `cd`. Use `WORKDIR`.
* **DL3006:** Always pin image references.
* **DL3020:** Use `COPY`, not `ADD` (unless extracting tarballs).