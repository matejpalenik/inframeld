//! The metadata opt-out keeps its pre-existing body-only public signature.
use inframeld_sdk_body_only_check::{HttpClient, types::CurrentSessionResponse};

async fn session(client: &HttpClient) {
    let _: CurrentSessionResponse = client.get_current_session().await.unwrap();
}

fn main() {
    let _ = session;
}
