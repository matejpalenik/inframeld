use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct DriverRequest {
    pub version: u32,
    pub profile: String,
    pub case_id: String,
    pub base_url: String,
    pub calls: Vec<Call>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Call {
    pub id: String,
    pub operation: String,
    pub headers: BTreeMap<String, String>,
    pub body: Option<Value>,
    pub query: Option<Value>,
    pub path: Option<Value>,
    pub timeout: u64,
    #[serde(rename = "uncheckedModel")]
    pub _unchecked_model: Option<bool>,
}
#[derive(Serialize)]
pub struct WireValue {
    pub encoding: String,
    pub value: String,
}
impl WireValue {
    pub fn bytes(value: &[u8]) -> Self {
        match std::str::from_utf8(value) {
            Ok(text) => Self::utf8(text.into()),
            Err(_) => Self {
                encoding: "base64".into(),
                value: base64::engine::general_purpose::STANDARD.encode(value),
            },
        }
    }
    pub fn utf8(value: String) -> Self {
        Self {
            encoding: "utf8".into(),
            value,
        }
    }
}
#[derive(Serialize)]
pub struct Header {
    pub name: String,
    #[serde(flatten)]
    pub data: WireValue,
}
pub fn headers(values: &reqwest::header::HeaderMap) -> Vec<Header> {
    values
        .iter()
        .map(|(name, value)| Header {
            name: name.to_string(),
            data: match value.to_str() {
                Ok(text) => WireValue::utf8(text.into()),
                Err(_) => WireValue {
                    encoding: "base64".into(),
                    value: base64::engine::general_purpose::STANDARD.encode(value.as_bytes()),
                },
            },
        })
        .collect()
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Observation {
    pub kind: String,
    pub call_id: String,
    pub validation: String,
    pub headers: Vec<Header>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub body: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub raw: Option<WireValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cause: Option<String>,
}
impl Default for Observation {
    fn default() -> Self {
        Self {
            kind: "sdk-error".into(),
            call_id: String::new(),
            validation: "none".into(),
            headers: Vec::new(),
            status: None,
            body: None,
            raw: None,
            error: None,
            cause: None,
        }
    }
}
