use inframeld_sdk::client::*;
use inframeld_sdk_test_rust::client as fixture;
use serde_json::Value;
pub(crate) trait Problem {
    fn json(&self) -> Value;
    fn validation(&self) -> &'static str {
        "generated-model"
    }
}
impl Problem for serde_json::Value {
    fn validation(&self) -> &'static str {
        "parsed-json"
    }
    fn json(&self) -> Value {
        self.clone()
    }
}
macro_rules! problems {
    ($kind:ty, $($variant:path),+) => {
        impl Problem for $kind {
            fn json(&self) -> Value {
                match self { $( $variant(problem) => serde_json::to_value(problem).unwrap(), )+ }
            }
        }
    };
}
problems!(
    GetCurrentSessionApiError,
    GetCurrentSessionApiError::Status400,
    GetCurrentSessionApiError::Status401,
    GetCurrentSessionApiError::Status403,
    GetCurrentSessionApiError::Status503
);
problems!(GetHealthApiError, GetHealthApiError::Status500);
problems!(
    InspectHumanOAuthConsentApiError,
    InspectHumanOAuthConsentApiError::Status400,
    InspectHumanOAuthConsentApiError::Status401,
    InspectHumanOAuthConsentApiError::Status403,
    InspectHumanOAuthConsentApiError::Status404,
    InspectHumanOAuthConsentApiError::Status422,
    InspectHumanOAuthConsentApiError::Status503
);
problems!(
    DecideHumanOAuthConsentApiError,
    DecideHumanOAuthConsentApiError::Status400,
    DecideHumanOAuthConsentApiError::Status401,
    DecideHumanOAuthConsentApiError::Status403,
    DecideHumanOAuthConsentApiError::Status404,
    DecideHumanOAuthConsentApiError::Status422,
    DecideHumanOAuthConsentApiError::Status503
);
problems!(
    AssignProjectUseOnlyGrantApiError,
    AssignProjectUseOnlyGrantApiError::Status400,
    AssignProjectUseOnlyGrantApiError::Status401,
    AssignProjectUseOnlyGrantApiError::Status403,
    AssignProjectUseOnlyGrantApiError::Status404,
    AssignProjectUseOnlyGrantApiError::Status409,
    AssignProjectUseOnlyGrantApiError::Status422,
    AssignProjectUseOnlyGrantApiError::Status503
);
problems!(
    fixture::ContractFixtureFallbackApiError,
    fixture::ContractFixtureFallbackApiError::Default
);
problems!(
    fixture::ContractFixtureVariantsApiError,
    fixture::ContractFixtureVariantsApiError::Default
);
problems!(
    fixture::ContractFixturePayloadApiError,
    fixture::ContractFixturePayloadApiError::Status422
);
problems!(
    fixture::ContractFixturePageApiError,
    fixture::ContractFixturePageApiError::Status422
);
problems!(
    fixture::ContractFixtureUploadApiError,
    fixture::ContractFixtureUploadApiError::Status422
);

macro_rules! observed {
    ($result:expr) => {
        match $result {
            Ok(value) => Observation {
                kind: "success".into(),
                validation: "generated-model".into(),
                status: Some(value.status),
                body: Some(serde_json::to_value(value.body).unwrap()),
                headers: headers(&value.headers),
                ..Default::default()
            },
            Err(error) => {
                let message = error.to_string();
                match error.api() {
                    Some(api) => Observation {
                        status: Some(api.status),
                        body: api.typed.as_ref().map(Problem::json),
                        raw: Some(WireValue::bytes(&api.raw_body)),
                        cause: api.parse_error.clone(),
                        validation: api
                            .typed
                            .as_ref()
                            .map(Problem::validation)
                            .unwrap_or("none")
                            .into(),
                        error: Some(message),
                        headers: headers(&api.headers),
                        ..Default::default()
                    },
                    None => Observation {
                        error: Some(message),
                        cause: Some(format!("{error:?}")),
                        ..Default::default()
                    },
                }
            }
        }
    };
}

pub(crate) use observed;

problems!(
    GetProtectedResourceMetadataApiError,
    GetProtectedResourceMetadataApiError::Status422,
    GetProtectedResourceMetadataApiError::Status404,
    GetProtectedResourceMetadataApiError::Status503
);
problems!(
    GetProtectedResourceMetadataForPathApiError,
    GetProtectedResourceMetadataForPathApiError::Status422,
    GetProtectedResourceMetadataForPathApiError::Status404,
    GetProtectedResourceMetadataForPathApiError::Status503
);
