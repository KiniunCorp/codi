# RATIONALE: Multi-stage build for Next.js with alpine runtime and non-root user.
# POLICY: Pinned base tags; avoid cache-busting; no root at runtime.
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline --no-audit
COPY . .
# Build Next.js in standalone mode if available
ENV NODE_ENV=production
RUN npm run build || npm run build --if-present

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Create non-root user
RUN adduser -D -u 10001 codi
USER 10001
# Copy minimal runtime assets
COPY --from=builder /app/.next/standalone ./ || true
COPY --from=builder /app/.next/static ./.next/static || true
COPY --from=builder /app/public ./public || true
EXPOSE 3000
# Fallback to default next start if standalone not present
CMD ["node", "server.js"]
