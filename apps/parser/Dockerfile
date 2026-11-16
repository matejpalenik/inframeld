FROM docker.io/library/python:3.13.18-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS builder

ARG TARGETARCH
RUN test "$TARGETARCH" = amd64 \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
        gcc libc6-dev libcap-dev=1:2.75-10+deb13u1+b3 libseccomp-dev=2.6.0-2 \
        meson ninja-build patch=2.8-2 pkg-config xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=parser_sources /bubblewrap-0.13.1.tar.xz /build/
COPY apps/parser/security/child-seccomp.c apps/parser/security/bubblewrap-reopen-proc-fd.patch /build/
WORKDIR /build
# Preserve the exact separately verified patch from upstream Bubblewrap PR 769.
RUN --network=none echo '0e85c8702248b8dd64144f594147553650cdd0e4c951690345faace79c217c4d  bubblewrap-0.13.1.tar.xz' | sha256sum -c - \
    && echo 'f759fa728378c38227f6d0cc7ee55581252572553445f7c0c7f91ed60f1117ef  bubblewrap-reopen-proc-fd.patch' | sha256sum -c - \
    && tar -xf bubblewrap-0.13.1.tar.xz \
    && patch --batch --forward --fuzz=0 --strip=1 --directory=bubblewrap-0.13.1 <bubblewrap-reopen-proc-fd.patch \
    && meson setup out bubblewrap-0.13.1 -Dselinux=disabled -Dtests=false -Dman=disabled \
        -Dbash_completion=disabled -Dzsh_completion=disabled \
    && meson compile -C out \
    && gcc -Wall -Wextra -Werror -O2 child-seccomp.c -lseccomp -o child-seccomp \
    && ./child-seccomp >child-seccomp.bpf \
    && test -s child-seccomp.bpf \
    && test ! -u out/bwrap \
    && install -m 0555 /usr/lib/x86_64-linux-gnu/libcap.so.2 /build/libcap.so.2

FROM docker.io/library/python:3.13.18-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS sandbox-probe

COPY --from=builder /build/libcap.so.2 /usr/lib/x86_64-linux-gnu/libcap.so.2
COPY --from=builder --chmod=0555 /build/out/bwrap /opt/probe-tools/bwrap
COPY --from=builder --chmod=0444 /build/child-seccomp.bpf /probe/security/child-seccomp.bpf
COPY --chmod=0444 apps/parser/security/oci-seccomp.json /probe/security/oci-seccomp.json
COPY --chmod=0444 apps/parser/tests/test_sandbox_boundaries.py /probe/tests/test_sandbox_boundaries.py
COPY --chmod=0444 apps/parser/security/oci-seccomp.json /probe-denied

USER 10001:10001
WORKDIR /probe
ENV INFRAMELD_PARSER_SANDBOX_TEST=1
ENTRYPOINT ["/usr/local/bin/python", "-IB", "-m", "unittest", "discover", "-s", "tests", "-v", "-f"]
