//! Declare the one explicit preference being saved.
use clap::Args;

#[derive(Debug, Args)]
pub(crate) struct Arguments {
    /// Registered target to remember. This does not edit shell variables.
    #[arg(conflicts_with = "target")]
    pub label: String,
}

use super::{Data, Plan, Report, Warning};
use crate::targets::{Change, SelectionSource, Store, TargetError, resolve, validate_label};
use std::sync::atomic::AtomicU8;

pub(super) fn plan(arguments: Arguments, store: &Store) -> Result<Data, TargetError> {
    validate_label(&arguments.label)?;
    let state = store.load()?;
    if !state.targets.contains_key(&arguments.label) {
        return Err(TargetError::NotFound);
    }
    Ok(Data::Plan(Plan {
        operation: "target.use",
        requested_target: Some(arguments.label),
        api_url: None,
        effective_target: None,
        source: None,
        intended_effects: vec!["saveTargetPreference"],
        checks_performed: vec!["argumentsValidated", "savedRegistryRead"],
        remote_verification: "notPerformed",
    }))
}

/// Remember only this preference, then disclose any remaining shell override.
pub(super) async fn execute(arguments: Arguments, store: &Store, stop: &AtomicU8) -> Report {
    let update = match store
        .update(Change::Select(arguments.label.clone()), stop)
        .await
    {
        Ok(update) => update,
        Err(TargetError::Uncertain) => {
            return Report {
                data: Some(Data::Selection {
                    requested_target: arguments.label,
                    saved_target: None,
                    effective_target: None,
                    source: None,
                    save_status: "unconfirmed",
                }),
                error: Some(TargetError::Uncertain),
                warnings: vec![],
                exit: 1,
            };
        }
        Err(error) => return Report::failure(error),
    };
    let environment = std::env::var_os("INFRAMELD_TARGET");
    let selected = match &environment {
        Some(value) => value
            .to_str()
            .and_then(|value| resolve(&update.state, None, Some(value)).ok()),
        None => resolve(&update.state, None, None).ok(),
    };
    let mut warnings = vec![];
    if environment.is_some() {
        warnings.push(Warning { code: "environment_overrides_saved_target", message: "This shell still selects through INFRAMELD_TARGET. Unset it or pass --target on the next command." });
        if selected.is_none() {
            warnings.push(Warning { code: "effective_target_unresolved", message: "INFRAMELD_TARGET does not select a usable registered target. The explicit preference was saved." });
        }
    }
    let source = selected
        .as_ref()
        .map(|(_, source)| *source)
        .or(environment.as_ref().map(|_| SelectionSource::Environment));
    Report {
        data: Some(Data::Selection {
            requested_target: arguments.label,
            saved_target: update.state.selected_target,
            effective_target: selected.map(|(target, _)| target.label),
            source,
            save_status: if update.changed { "saved" } else { "unchanged" },
        }),
        error: None,
        warnings,
        exit: 0,
    }
}
