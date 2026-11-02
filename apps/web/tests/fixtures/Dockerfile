FROM docker.io/library/node:26.6.0-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libnss3-tools \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global pnpm@12.4.0
WORKDIR /workspace
COPY . .
RUN pnpm install --frozen-lockfile \
    && pnpm --filter @inframeld/sdk --fail-if-no-match build \
    && pnpm --filter @inframeld/web --fail-if-no-match build \
    && pnpm --filter @inframeld/web --fail-if-no-match exec playwright install --with-deps chromium
RUN test -s /workspace/apps/web/.next/BUILD_ID \
    && chmod 755 /workspace \
    && groupadd --gid 10001 fixture \
    && useradd --uid 10001 --gid fixture --create-home fixture \
    && mkdir -p /workspace/apps/web/.next \
    && chown -R fixture:fixture /workspace/apps/web/.next
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/account-browsers
# Move the package-selected browser into a public, fixed image path.
RUN mv /root/.cache/ms-playwright /opt/account-browsers \
    && chmod -R a+rX /opt/account-browsers
USER fixture:fixture
WORKDIR /workspace/apps/web
