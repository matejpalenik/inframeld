# Inframeld Rust SDK

The generated client follows Inframeld's native OpenAPI contract. This package remains version `0.0.0` with publication protection. Building or consuming it requires neither the backend nor a generator. Registry publication and server-version compatibility remain separate work.

Use generated operations and models. `HttpClient::new()` and `Default` honor the configured timeout, currently five seconds, and disable redirects/retries. `with_client` preserves the supplied reqwest transport, including deliberate timeout/redirect/retry overrides. Supply the server URL and credentials. Success results expose `status`, `headers` and `body`. HTTP errors retain typed Problem Details when decoding succeeds, raw bytes and convenient text diagnostics. Transport errors can have no HTTP response. Dropping an active future cancels that operation. A lost response does not authorize redispatch.

Main JSON operations with multiple response shapes expose a generated response enum selected by exact status, then class/default, and media type. Nullable payloads and bodyless unit variants stay distinct. Inspect the generated operation for its exact return type.

The example below is the complete, statically compiled [consumer fixture](../sdk-tools/consumers/rust/src/main.rs). It exercises success, inspectable authentication failure and client reuse against a local backend. Replace its fixture credential for actual use.

## Build and use locally

```sh
cargo build --locked -p inframeld-sdk
cargo package --locked --allow-dirty --no-verify -p inframeld-sdk
```

Rust/TypeScript consumers take the fixture base URL as their first argument. Python uses the same argument. The examples expect the controlled conformance backend, while application callers supply their own server URL and credentials.

```rust
//! Exercise an unpacked crate through its generated public operations.
use inframeld_sdk::HttpClient;
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let base = std::env::args().nth(1).expect("base URL");
    let transport = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .redirect(reqwest::redirect::Policy::none())
        .retry(reqwest::retry::never())
        .no_proxy()
        .build()?;
    let client = HttpClient::with_client(transport).with_base_url(base);
    let health = client.get_health().await?;
    assert_eq!(health.status, 200);
    assert_eq!(health.body.additional_properties["status"], "ok");
    let rejection = client.get_current_session().await.unwrap_err();
    let context = rejection.api().expect("HTTP context");
    assert_eq!(context.status, 401);
    assert!(context.typed.is_some());
    assert!(!context.raw_body.is_empty());
    assert!(context.headers.contains_key("www-authenticate"));
    let authenticated = client
        .clone()
        .with_header("Authorization", "Bearer sdk-human");
    let session = authenticated.get_current_session().await?;
    assert_eq!(session.status, 200);
    assert_eq!(
        session.body.principal_id.to_string(),
        "00000000-0000-4000-8000-000000000001"
    );
    assert_eq!(client.get_health().await?.status, 200);
    Ok(())
}
```

## Maintain generation

Generation is explicit. Follow the [SDK runbook](../sdk-tools/README.md) for verified inputs, drift, native checks and package consumers. Fixtures and development tooling are outside this distribution. Fix generator source or shipped resources before regeneration, never generated SDK output. See the [response-fix evidence](../../docs/development/reports/sdk-response-fixes-verification.md) for actually executed checks and platform limits.
