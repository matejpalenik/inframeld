//! Declare the one explicit preference being saved.
use clap::Args;

#[derive(Debug, Args)]
pub(crate) struct Arguments {
    /// Registered target to remember. This does not edit shell variables.
    #[arg(conflicts_with = "target")]
    pub label: String,
}

use super::{
    ChangeKind, Data, Destination, Plan, PreferenceChange, Report, UnresolvedFact, Warning,
};
use crate::targets::{
    Change, SelectionSource, State, Store, TargetError, Update, resolve, validate_label,
};
use std::{ffi::OsStr, sync::atomic::AtomicU8};

pub(super) fn plan(arguments: Arguments, store: &Store) -> Result<Report, TargetError> {
    validate_label(&arguments.label)?;
    let state = store.load()?;
    if !state.targets.contains_key(&arguments.label) {
        return Err(TargetError::NotFound);
    }
    let environment = std::env::var_os("INFRAMELD_TARGET");
    let (effective_target, source) = effective(&state, environment.as_deref());
    let mut unresolved_facts = vec![
        UnresolvedFact::PersistenceNotPerformed,
        UnresolvedFact::RemoteHealthUnverified,
    ];
    if environment.is_some() && effective_target.is_none() {
        unresolved_facts.push(UnresolvedFact::EffectiveTargetUnresolved);
    }
    let warnings = override_warnings(
        environment.is_some(),
        effective_target.is_none(),
        "INFRAMELD_TARGET does not select a usable registered target. This preview has not saved a preference.",
    );
    let changes = vec![PreferenceChange::new(
        ChangeKind::Proposed,
        state.selected_target,
        Some(arguments.label.clone()),
    )];
    let mut report = Report::success(Data::Plan(Plan {
        operation: "target.use",
        requested_target: Some(arguments.label),
        api_url: None,
        effective_target,
        source,
        intended_effects: vec!["saveTargetPreference"],
        checks_performed: vec!["argumentsValidated", "savedRegistryRead"],
        remote_verification: "notPerformed",
        changes,
        outgoing_data_categories: vec![],
        destinations: vec![Destination::LocalTargetRegistry],
        unresolved_facts,
    }));
    report.warnings = warnings;
    Ok(report)
}

/// Remember only this preference, then disclose any remaining shell override.
pub(super) async fn execute(arguments: Arguments, store: &Store, stop: &AtomicU8) -> Report {
    let update = store
        .update(Change::Select(arguments.label.clone()), stop)
        .await;
    let environment = std::env::var_os("INFRAMELD_TARGET");
    selection_report(arguments.label, update, environment.as_deref())
}

/// Report only the update's own observations, without rereading a possibly newer preference.
fn selection_report(
    requested: String,
    result: Result<Update, TargetError>,
    environment: Option<&OsStr>,
) -> Report {
    let update = match result {
        Ok(update) => update,
        Err(TargetError::Uncertain) => {
            return Report {
                data: Some(Data::Selection {
                    requested_target: requested,
                    saved_target: None,
                    effective_target: None,
                    source: None,
                    save_status: "unconfirmed",
                    changes: vec![],
                }),
                error: Some(TargetError::Uncertain),
                warnings: vec![],
                exit: 1,
            };
        }
        Err(error) => return Report::failure(error),
    };
    let (effective_target, source) = effective(&update.state, environment);
    let warnings = override_warnings(
        environment.is_some(),
        effective_target.is_none(),
        "INFRAMELD_TARGET does not select a usable registered target. The explicit preference was saved.",
    );
    let changes = if update.changed {
        vec![PreferenceChange::new(
            ChangeKind::Confirmed,
            update.previous_selected_target,
            update.state.selected_target.clone(),
        )]
    } else {
        vec![]
    };
    Report {
        data: Some(Data::Selection {
            requested_target: requested,
            saved_target: update.state.selected_target,
            effective_target,
            source,
            save_status: if update.changed { "saved" } else { "unchanged" },
            changes,
        }),
        error: None,
        warnings,
        exit: 0,
    }
}

fn effective(
    state: &State,
    environment: Option<&OsStr>,
) -> (Option<String>, Option<SelectionSource>) {
    let selected = match environment {
        Some(value) => value
            .to_str()
            .and_then(|value| resolve(state, None, Some(value)).ok()),
        None => resolve(state, None, None).ok(),
    };
    let source = selected
        .as_ref()
        .map(|(_, source)| *source)
        .or(environment.map(|_| SelectionSource::Environment));
    (selected.map(|(target, _)| target.label), source)
}

fn override_warnings(
    overridden: bool,
    unresolved: bool,
    unresolved_message: &'static str,
) -> Vec<Warning> {
    let mut warnings = vec![];
    if overridden {
        warnings.push(Warning { code: "environment_overrides_saved_target", message: "This shell still selects through INFRAMELD_TARGET. Unset it or pass --target on the next command." });
        if unresolved {
            warnings.push(Warning {
                code: "effective_target_unresolved",
                message: unresolved_message,
            });
        }
    }
    warnings
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;
    use crate::targets::{Target, Transport};
    use serde_json::json;
    use tempfile::TempDir;

    #[test]
    fn unconfirmed_persistence_retains_the_request_without_a_completed_change() {
        let report = selection_report("dev".into(), Err(TargetError::Uncertain), None);
        assert_eq!(report.exit, 1);
        assert!(matches!(report.error, Some(TargetError::Uncertain)));
        let data = serde_json::to_value(&report.data).unwrap();
        assert_eq!(data["requestedTarget"], "dev");
        assert_eq!(data["saveStatus"], "unconfirmed");
        assert_eq!(data["savedTarget"], serde_json::Value::Null);
        assert_eq!(data["effectiveTarget"], serde_json::Value::Null);
        assert_eq!(data["changes"], json!([]));
        assert!(!report.human().contains("Before / Now"));
    }

    #[tokio::test]
    async fn interruption_keeps_the_already_confirmed_locked_change() {
        let home = TempDir::new().unwrap();
        let store = Store {
            directory: home.path().join("inframeld"),
        };
        let stop = AtomicU8::new(0);
        for label in ["dev", "prod"] {
            store
                .update(
                    Change::Register(Target {
                        label: label.into(),
                        installation_id: uuid::Uuid::from_u128(42),
                        api_url: "https://api.example.test".into(),
                        issuer_url: "https://identity.example.test".into(),
                        client_id: "inframeld-cli".into(),
                        transport: Transport::default(),
                    }),
                    &stop,
                )
                .await
                .unwrap();
        }
        store
            .update(Change::Select("prod".into()), &stop)
            .await
            .unwrap();
        let result = store.update(Change::Select("dev".into()), &stop).await;
        let report = selection_report("dev".into(), result, None).observe_stop(130);
        assert_eq!(report.exit, 130);
        assert!(matches!(report.error, Some(TargetError::Interrupted)));
        let data = serde_json::to_value(&report.data).unwrap();
        assert_eq!(data["saveStatus"], "saved");
        assert_eq!(data["changes"][0]["kind"], "confirmed");
        assert_eq!(
            data["changes"][0]["fields"][0]["before"],
            json!({"known":true,"value":"prod"})
        );
        assert_eq!(
            data["changes"][0]["fields"][0]["after"],
            json!({"known":true,"value":"dev"})
        );
        assert_eq!(
            store.load().unwrap().selected_target.as_deref(),
            Some("dev")
        );
    }
}
