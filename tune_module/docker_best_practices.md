# DOCKER OPTIMIZATION CONSTITUTION & BEST PRACTICES
*Version 1.0 | Based on CIS Benchmarks v1.6.0, BuildKit Documentation, and Hadolint Standards*

## I. SECURITY PROTOCOL (CIS & CRITICAL SECURITY)
**Goal:** Zero known vulnerabilities, minimized attack surface, and non-privileged execution.

1.  **Non-Root User Enforcement (CIS 4.1)**
    * **Rule:** The container must NOT run as root.
    * **Implementation:** Create a user (UID > 1000) and switch to it at the end of the Dockerfile.
    * **Pattern:** `RUN groupadd -r app && useradd -r -g app app` followed by `USER app`.

2.  **Base Image Provenance (CIS 4.6)**
    * **Rule:** Do not use `latest` tags. They are mutable and break reproducibility.
    * **Implementation:** Pin specific versions (e.g., `node:18.16.0-alpine`). Ideally, use SHA256 digests for high-security contexts.
    * **Reasoning:** Prevents supply chain attacks where a tag is overwritten with malicious code.

3.  **Least Privilege Dependencies**
    * **Rule:** Do not install `sudo`, `curl`, `wget`, or `vim` in the final production image.
    * **Reasoning:** "Living off the Land" binaries help attackers move laterally if the container is breached.

4.  **Secrets & Environment**
    * **Rule:** NEVER use `ENV` to store secrets (API keys, passwords). They persist in image history.
    * **Implementation:** Use build arguments (`ARG`) that are not persisted, or mount secrets at runtime.

---

## II. PERFORMANCE ARCHITECTURE (SIZE & SPEED)
**Goal:** Minimal final image size (<200MB for microservices) and maximized build cache hit rate.

1.  **Mandatory Multi-Stage Builds**
    * **Rule:** Separate the `build` environment (compilers, dev dependencies) from the `runtime` environment.
    * **Structure:**
        * `Stage 1 (Builder):` Install full CLI tools, compilers, headers.
        * `Stage 2 (Production):` Copy *only* compiled artifacts/node_modules from Stage 1.
    * **Target:** Final image should rely on `alpine` or `distroless` variants.

2.  **Layer Caching Strategy**
    * **Rule:** Order instructions from "Least Likely to Change" to "Most Likely to Change".
    * **Correct Order:**
        1.  `COPY package.json .` (Dependencies definition)
        2.  `RUN npm install` (Install dependencies - Cached unless package.json changes)
        3.  `COPY . .` (Source code - Changes every commit)
    * **Anti-Pattern:** `COPY . .` followed by `RUN npm install` breaks the cache on every code change.

3.  **Package Manager Hygiene**
    * **Debian/Ubuntu:** `apt-get update && apt-get install -y --no-install-recommends <pkgs> && rm -rf /var/lib/apt/lists/*`
    * **Alpine:** `apk add --no-cache <pkgs>`
    * **Why:** Installing "recommended" packages bloats images by 30-50%. Leaving apt-lists wastes ~40MB.

4.  **BuildKit Caching**
    * **Rule:** Use cache mounts for package managers to speed up repeated builds.
    * **Pattern:** `RUN --mount=type=cache,target=/root/.npm npm ci`

---

## III. SYNTAX & LOGIC (HADOLINT STANDARD)
**Goal:** Clean, readable, and error-free code (Lint Score: 10/10).

| Rule ID | Severity | Description | Fix |
| :--- | :--- | :--- | :--- |
| **DL3000** | Error | Absolute WORKDIR | Use `WORKDIR /app` instead of `WORKDIR app`. |
| **DL3003** | Warning | No `cd` usage | Do not use `RUN cd /app && npm i`. Use `WORKDIR /app` globally. |
| **DL3006** | Warning | Always Pin Image | Never `FROM node`. Always `FROM node:18-alpine`. |
| **DL3008** | Warning | Pin Apt Version | `apt-get install python3=3.8.*`. |
| **DL3009** | Info | Delete Apt Lists | Run `rm -rf /var/lib/apt/lists/*` in the *same layer* as install. |
| **DL3018** | Warning | Pin Apk Version | `apk add --no-cache nodejs=18.16.0-r0`. |
| **DL3020** | Error | COPY vs ADD | Use `COPY`. Only use `ADD` if unzipping a tarball automatically. |

---

## IV. TECH-SPECIFIC STANDARDS

### A. Node.js
* **Env:** Set `ENV NODE_ENV=production`.
* **PID 1:** Use `tini` or `dumb-init` if not using a full process manager, or ensure `node` is run directly via `CMD ["node", "app.js"]` (exec form), not `CMD npm start`.
* **Clean:** Run `npm prune --production` before copying to final stage.

### B. Python
* **Buffering:** Set `ENV PYTHONUNBUFFERED=1` to ensure logs stream to Docker immediately.
* **Virtual Envs:** Use `venv` even in Docker to isolate from system Python, OR use `--user` install.
* **Clean:** Disable pip cache: `pip install --no-cache-dir -r requirements.txt`.

### C. Java
* **Base:** Use `eclipse-temurin:XX-jre-alpine` (JRE only) for the final stage, not the full JDK.
* **Exploded Jar:** For Spring Boot, unpack the jar to allow faster startup and better layering.
* **User:** Java often runs as root by default in containers; strictly enforce `USER 1001`.
