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
problems!(
    GetMyOrganizationAccessApiError,
    GetMyOrganizationAccessApiError::Status400,
    GetMyOrganizationAccessApiError::Status401,
    GetMyOrganizationAccessApiError::Status403,
    GetMyOrganizationAccessApiError::Status404,
    GetMyOrganizationAccessApiError::Status503
);
problems!(
    CreateProjectApiError,
    CreateProjectApiError::Status400,
    CreateProjectApiError::Status401,
    CreateProjectApiError::Status403,
    CreateProjectApiError::Status404,
    CreateProjectApiError::Status409,
    CreateProjectApiError::Status413,
    CreateProjectApiError::Status415,
    CreateProjectApiError::Status422,
    CreateProjectApiError::Status503
);
problems!(
    AdmitHumanApiError,
    AdmitHumanApiError::Status400,
    AdmitHumanApiError::Status401,
    AdmitHumanApiError::Status403,
    AdmitHumanApiError::Status404,
    AdmitHumanApiError::Status409,
    AdmitHumanApiError::Status413,
    AdmitHumanApiError::Status415,
    AdmitHumanApiError::Status422,
    AdmitHumanApiError::Status503
);
problems!(
    AddProjectMemberApiError,
    AddProjectMemberApiError::Status400,
    AddProjectMemberApiError::Status401,
    AddProjectMemberApiError::Status403,
    AddProjectMemberApiError::Status404,
    AddProjectMemberApiError::Status409,
    AddProjectMemberApiError::Status413,
    AddProjectMemberApiError::Status415,
    AddProjectMemberApiError::Status422,
    AddProjectMemberApiError::Status503
);
problems!(
    RemoveProjectMemberApiError,
    RemoveProjectMemberApiError::Status400,
    RemoveProjectMemberApiError::Status401,
    RemoveProjectMemberApiError::Status403,
    RemoveProjectMemberApiError::Status404,
    RemoveProjectMemberApiError::Status409,
    RemoveProjectMemberApiError::Status422,
    RemoveProjectMemberApiError::Status503
);
problems!(GetHealthApiError, GetHealthApiError::Status500);
problems!(
    ListProjectActionGrantsApiError,
    ListProjectActionGrantsApiError::Status400,
    ListProjectActionGrantsApiError::Status401,
    ListProjectActionGrantsApiError::Status403,
    ListProjectActionGrantsApiError::Status404,
    ListProjectActionGrantsApiError::Status422,
    ListProjectActionGrantsApiError::Status503
);
problems!(
    GetMyProjectAccessApiError,
    GetMyProjectAccessApiError::Status400,
    GetMyProjectAccessApiError::Status401,
    GetMyProjectAccessApiError::Status403,
    GetMyProjectAccessApiError::Status404,
    GetMyProjectAccessApiError::Status422,
    GetMyProjectAccessApiError::Status503
);
problems!(
    SetProjectActionGrantApiError,
    SetProjectActionGrantApiError::Status400,
    SetProjectActionGrantApiError::Status401,
    SetProjectActionGrantApiError::Status403,
    SetProjectActionGrantApiError::Status404,
    SetProjectActionGrantApiError::Status409,
    SetProjectActionGrantApiError::Status413,
    SetProjectActionGrantApiError::Status415,
    SetProjectActionGrantApiError::Status422,
    SetProjectActionGrantApiError::Status503
);
problems!(
    RemoveProjectActionGrantApiError,
    RemoveProjectActionGrantApiError::Status400,
    RemoveProjectActionGrantApiError::Status401,
    RemoveProjectActionGrantApiError::Status403,
    RemoveProjectActionGrantApiError::Status404,
    RemoveProjectActionGrantApiError::Status409,
    RemoveProjectActionGrantApiError::Status422,
    RemoveProjectActionGrantApiError::Status503
);
problems!(
    ListProjectMembersApiError,
    ListProjectMembersApiError::Status400,
    ListProjectMembersApiError::Status401,
    ListProjectMembersApiError::Status403,
    ListProjectMembersApiError::Status404,
    ListProjectMembersApiError::Status422,
    ListProjectMembersApiError::Status503
);
problems!(
    GetDeletionStatusApiError,
    GetDeletionStatusApiError::Status400,
    GetDeletionStatusApiError::Status401,
    GetDeletionStatusApiError::Status403,
    GetDeletionStatusApiError::Status422,
    GetDeletionStatusApiError::Status500,
    GetDeletionStatusApiError::Status503
);
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

problems!(
    LookupOriginalOperationApiError,
    LookupOriginalOperationApiError::Status400,
    LookupOriginalOperationApiError::Status401,
    LookupOriginalOperationApiError::Status403,
    LookupOriginalOperationApiError::Status404,
    LookupOriginalOperationApiError::Status413,
    LookupOriginalOperationApiError::Status415,
    LookupOriginalOperationApiError::Status422,
    LookupOriginalOperationApiError::Status503
);

problems!(
    ResolveProjectNameApiError,
    ResolveProjectNameApiError::Status400,
    ResolveProjectNameApiError::Status401,
    ResolveProjectNameApiError::Status403,
    ResolveProjectNameApiError::Status404,
    ResolveProjectNameApiError::Status409,
    ResolveProjectNameApiError::Status422,
    ResolveProjectNameApiError::Status503
);

problems!(
    GetProjectMetadataApiError,
    GetProjectMetadataApiError::Status400,
    GetProjectMetadataApiError::Status401,
    GetProjectMetadataApiError::Status403,
    GetProjectMetadataApiError::Status404,
    GetProjectMetadataApiError::Status409,
    GetProjectMetadataApiError::Status422,
    GetProjectMetadataApiError::Status503
);

problems!(
    UpdateProjectMetadataApiError,
    UpdateProjectMetadataApiError::Status400,
    UpdateProjectMetadataApiError::Status401,
    UpdateProjectMetadataApiError::Status403,
    UpdateProjectMetadataApiError::Status404,
    UpdateProjectMetadataApiError::Status409,
    UpdateProjectMetadataApiError::Status413,
    UpdateProjectMetadataApiError::Status415,
    UpdateProjectMetadataApiError::Status422,
    UpdateProjectMetadataApiError::Status503
);
