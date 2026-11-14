FROM docker.io/library/node:26.6.0-bookworm-slim@sha256:81502e860176e63695d769d3d1a2d3a403abc1c27c6a02169b765f3e43b60ede AS build

WORKDIR /workspace
RUN npm install --global pnpm@12.4.0

COPY .npmrc package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/sdk-typescript/package.json packages/sdk-typescript/package.json
RUN pnpm install --frozen-lockfile

COPY apps/web apps/web
COPY packages/sdk-typescript packages/sdk-typescript
RUN INFRAMELD_ACCOUNT_STANDALONE_BUILD=1 pnpm --filter @inframeld/web --fail-if-no-match build \
    && test -s apps/web/.next/standalone/apps/web/server.js \
    && test -d apps/web/.next/static

FROM docker.io/library/node:26.13.1-bookworm-slim@sha256:5df79989ed685e09f0a98019db4cebfb22fb9df1a53c0161664a011f7ff6b0f1

RUN groupadd --gid 10001 account \
    && useradd --uid 10001 --gid account --no-create-home account

COPY --from=build /workspace/apps/web/.next/standalone/ /app/
COPY --from=build /workspace/apps/web/public/ /app/apps/web/public/
COPY --from=build /workspace/apps/web/.next/static/ /app/apps/web/.next/static/

ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app/apps/web
USER 10001:10001
CMD ["node", "server.js"]
