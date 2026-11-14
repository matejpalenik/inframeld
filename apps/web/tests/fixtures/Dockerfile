FROM docker.io/library/node:26.6.0-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libnss3-tools \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global pnpm@12.4.0
WORKDIR /workspace
COPY . .
ARG ACCOUNT_FIXTURE_BUILD_WEB=1
RUN pnpm install --frozen-lockfile \
    && if [ "$ACCOUNT_FIXTURE_BUILD_WEB" = 1 ]; then \
        pnpm --filter @inframeld/web --fail-if-no-match build \
        && test -s /workspace/apps/web/.next/BUILD_ID; \
    else \
        pnpm --filter @inframeld/sdk --fail-if-no-match build; \
    fi \
    && pnpm --filter @inframeld/web --fail-if-no-match exec playwright install --with-deps chromium
RUN chmod 755 /workspace \
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
CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0"]
