//! Native calls only. Shared TypeScript tests own all conformance assertions.
mod lifecycle;
mod models;
mod observation;
mod operations;
mod protocol;

use protocol::DriverRequest;
use serde_json::json;
use std::{io::Read, time::Duration};
const BINDINGS: &[&str] = &[
    "getProtectedResourceMetadata",
    "getProtectedResourceMetadataForPath",
    "getHealth",
    "getCurrentSession",
    "inspectHumanOAuthConsent",
    "decideHumanOAuthConsent",
    "assignProjectUseOnlyGrant",
    "lookupOriginalOperation",
    "contractFixturePayload",
    "contractFixturePage",
    "contractFixtureUpload",
    "contractFixtureNullable",
    "contractFixtureEmpty",
    "contractFixtureVariants",
    "contractFixtureMedia",
    "contractFixtureFallback",
];

#[tokio::main]
async fn main() {
    if std::env::args().nth(1).as_deref() == Some("--bindings") {
        println!("{}", json!(BINDINGS));
        return;
    }
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).unwrap();
    let request: DriverRequest = serde_json::from_str(&input).expect("Invalid driver request");
    assert_eq!(request.version, 2, "Unsupported driver protocol");
    assert_eq!(request.profile, "rust");
    let first = request.calls.first().expect("Empty call sequence");
    assert!(
        request
            .calls
            .iter()
            .all(|call| call.timeout == first.timeout),
        "A Rust client sequence uses one explicit transport timeout"
    );
    let transport = reqwest::Client::builder()
        .timeout(Duration::from_millis(first.timeout))
        .redirect(reqwest::redirect::Policy::none())
        .retry(reqwest::retry::never())
        .no_proxy()
        .build()
        .unwrap();
    let base_client =
        inframeld_sdk::HttpClient::with_client(transport.clone()).with_base_url(&request.base_url);
    let base_fixture = inframeld_sdk_test_rust::HttpClient::with_client(transport)
        .with_base_url(&request.base_url);
    let mut observations = Vec::new();
    for call in &request.calls {
        // Wrappers share the same reqwest pool. Per-call credentials/defaults
        // start from the caller's base configuration rather than leaking forward.
        let mut client = base_client.clone();
        let fixture = base_fixture.clone();
        let mut additional_headers = call.headers.clone();
        if matches!(
            call.operation.as_str(),
            "getCurrentSession" | "assignProjectUseOnlyGrant" | "lookupOriginalOperation"
        ) {
            if let Some(token) = call
                .headers
                .get("Authorization")
                .and_then(|value| value.strip_prefix("Bearer "))
            {
                client = client.with_api_key(token);
                additional_headers.remove("Authorization");
            }
        }
        // This header is a generated operation argument, not a default header.
        if call.operation == "assignProjectUseOnlyGrant" {
            additional_headers.remove("Idempotency-Key");
        }
        client = client.with_headers(additional_headers);
        let fixture = fixture.with_headers(call.headers.clone());
        let mut observation = operations::observe(&client, &fixture, call).await;
        observation.call_id = call.id.clone();
        observations.push(observation);
    }
    println!(
        "{}",
        json!({"version":2,"profile":request.profile,"caseId":request.case_id,"kind":"observations","observations":observations})
    );
}
