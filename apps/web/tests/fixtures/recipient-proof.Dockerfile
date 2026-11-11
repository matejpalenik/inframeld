ARG ACCOUNT_BACKEND_IMAGE
FROM docker.io/library/rust:1.95.0-bookworm AS proof-build
WORKDIR /source
COPY . .
ENV CARGO_BUILD_JOBS=2
RUN cargo build --locked -p inframeld-cli --bin inframeld \
      --example recipient_proof --example recipient_proof_native_driver \
    && mkdir /proof-bin \
    && cp target/debug/inframeld target/debug/examples/recipient_proof \
          target/debug/examples/recipient_proof_native_driver /proof-bin/ \
    && rustc --version --verbose > /proof-bin/compiler.txt \
    && cargo --version >> /proof-bin/compiler.txt \
    && sha256sum Cargo.lock > /proof-bin/cargo-lock.sha256 \
    && cd /proof-bin \
    && sha256sum inframeld recipient_proof recipient_proof_native_driver > artifacts.sha256

FROM ${ACCOUNT_BACKEND_IMAGE}
COPY --from=proof-build /proof-bin/ /opt/account-proof/bin/
