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
