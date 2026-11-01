//! Read local effective context without implying current TLS, login or permissions.
use super::{Data, Plan};
use crate::targets::{Store, TargetError, resolve};

pub(super) fn execute(store: &Store, explicit: Option<&str>) -> Result<Data, TargetError> {
    let environment = if explicit.is_none() {
        std::env::var("INFRAMELD_TARGET")
            .map(Some)
            .or_else(|error| {
                if matches!(error, std::env::VarError::NotPresent) {
                    Ok(None)
                } else {
                    Err(TargetError::InvalidLabel)
                }
            })?
    } else {
        None
    };
    let (target, source) = resolve(&store.load()?, explicit, environment.as_deref())?;
    Ok(Data::Inspection {
        target,
        source,
        verification: "savedBinding",
    })
}

pub(super) fn plan(store: &Store, explicit: Option<&str>) -> Result<Data, TargetError> {
    let Data::Inspection { target, source, .. } = execute(store, explicit)? else {
        return Err(TargetError::InvalidState);
    };
    Ok(Data::Plan(Plan {
        operation: "target.show",
        requested_target: None,
        api_url: None,
        effective_target: Some(target.label),
        source: Some(source),
        intended_effects: vec!["showSavedTarget"],
        checks_performed: vec!["argumentsValidated", "savedRegistryRead"],
        remote_verification: "notPerformed",
    }))
}
