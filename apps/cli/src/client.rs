//! Construction boundary for the generated SDK. No handwritten application requests.
use crate::context::Connection;
use inframeld_sdk::HttpClient;

/// Construct the generated transport from explicit context without sending a request.
#[must_use]
pub fn connect(connection: &Connection) -> HttpClient {
    HttpClient::new().with_base_url(&connection.base_url)
}
