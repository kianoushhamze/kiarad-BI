ARG NODE_BASE_IMAGE=node:22-slim
FROM ${NODE_BASE_IMAGE} AS dependencies
WORKDIR /app
COPY kiarad-dashboard/package.json kiarad-dashboard/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund \
    --fetch-retries=5 --fetch-retry-mintimeout=10000 \
    --fetch-retry-maxtimeout=60000 --fetch-timeout=120000

FROM ${NODE_BASE_IMAGE} AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY kiarad-dashboard/ ./
ARG KIARAD_API_URL=http://backend:8000
ARG NEXT_PUBLIC_API_URL=http://backend:8000
ENV KIARAD_API_URL=${KIARAD_API_URL} \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

FROM ${NODE_BASE_IMAGE} AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
