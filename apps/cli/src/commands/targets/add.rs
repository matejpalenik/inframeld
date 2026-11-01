//! Declare explicit credential-free target registration inputs.
use clap::Args;
use std::path::PathBuf;

#[derive(Debug, Args)]
pub(crate) struct Arguments {
    /// Local label for the new target.
    #[arg(conflicts_with = "target")]
    pub label: String,
    /// Exact canonical HTTPS API identity supplied by the operator.
    #[arg(long)]
    pub url: String,
    /// Operator-managed public PEM CA bundle, read afresh for each network attempt.
    #[arg(long = "ca-cert", value_name = "FILE")]
    pub ca_files: Vec<PathBuf>,
    /// Explicit credential-free HTTP(S) proxy origin.
    #[arg(long, value_name = "URL")]
    pub proxy: Option<String>,
}

use super::{Data, Plan, Report};
use crate::{
    discovery,
    targets::{Change, Store, Target, TargetError, Transport, validate_label},
};
use std::sync::atomic::AtomicU8;

fn inputs(arguments: &Arguments) -> Result<Transport, TargetError> {
    validate_label(&arguments.label)?;
    let transport = Transport::new(arguments.ca_files.clone(), arguments.proxy.clone())?;
    discovery::validate_saved_identity(&arguments.url, &arguments.url)
        .map_err(TargetError::InvalidApiUrl)?;
    Ok(transport)
}

pub(super) fn plan(arguments: Arguments, store: &Store) -> Result<Data, TargetError> {
    let transport = inputs(&arguments)?;
    transport.options()?;
    store.load()?;
    Ok(Data::Plan(Plan {
        operation: "target.add",
        requested_target: Some(arguments.label),
        api_url: Some(arguments.url),
        effective_target: None,
        source: None,
        intended_effects: vec!["registerTarget"],
        checks_performed: vec![
            "argumentsValidated",
            "savedRegistryRead",
            "transportInputsValidated",
        ],
        remote_verification: "notPerformed",
    }))
}

/// Validate anonymously before taking the local writer lock. No account is loaded.
pub(super) async fn execute(arguments: Arguments, store: &Store, stop: &AtomicU8) -> Report {
    let transport = match inputs(&arguments) {
        Ok(value) => value,
        Err(error) => return Report::failure(error),
    };
    let options = match transport.options() {
        Ok(options) => options,
        Err(error) => return Report::failure(error),
    };
    let discovered = match discovery::discover(&arguments.url, options).await {
        Ok(value) => value,
        Err(error) => return Report::failure(error.into()),
    };
    let target = Target {
        label: arguments.label,
        installation_id: discovered.installation_id,
        api_url: discovered.resource,
        issuer_url: discovered.provider.issuer().as_str().to_owned(),
        client_id: discovered.client_id.to_owned(),
        transport,
    };
    let update = store.update(Change::Register(target.clone()), stop).await;
    let (registration, error, exit) = match update {
        Ok(update) => (
            if update.changed {
                "saved"
            } else {
                "alreadyRegistered"
            },
            None,
            0,
        ),
        Err(TargetError::Uncertain) => ("unconfirmed", Some(TargetError::Uncertain), 1),
        Err(error) => return Report::failure(error),
    };
    Report {
        data: Some(Data::Registration {
            target,
            registration,
            selection_changed: false,
            verification: "discoveryValidated",
        }),
        error,
        warnings: vec![],
        exit,
    }
}
