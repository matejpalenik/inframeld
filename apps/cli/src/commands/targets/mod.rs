//! Manage public installation connections without authenticating or selecting Projects.

use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub(crate) struct Arguments {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub(crate) enum Command {
    /// Validate public discovery and save an explicitly named connection
    Add(add::Arguments),
    /// Save the preferred registered target without contacting it
    Use(use_target::Arguments),
    /// Show the effective registered target without contacting it
    Show,
}

mod add;
mod show;
mod use_target;

use crate::targets::{SelectionSource, Store, Target, TargetError};
use serde::{Serialize, Serializer, ser::SerializeStruct};
use std::{
    fmt::Write as _,
    io::Write,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU8, Ordering},
    },
};

#[derive(Debug, Clone, Serialize)]
pub(crate) struct Warning {
    pub code: &'static str,
    pub message: &'static str,
}

/// Command-local typed facts. They describe local effects, never authentication.
#[derive(Debug, Serialize)]
#[serde(untagged)]
pub(crate) enum Data {
    Registration {
        target: Target,
        registration: &'static str,
        #[serde(rename = "selectionChanged")]
        selection_changed: bool,
        verification: &'static str,
    },
    Selection {
        #[serde(rename = "requestedTarget")]
        requested_target: String,
        #[serde(rename = "savedTarget")]
        saved_target: Option<String>,
        #[serde(rename = "effectiveTarget")]
        effective_target: Option<String>,
        source: Option<SelectionSource>,
        #[serde(rename = "saveStatus")]
        save_status: &'static str,
        changes: Vec<PreferenceChange>,
    },
    Inspection {
        target: Target,
        source: SelectionSource,
        verification: &'static str,
    },
    Plan(Plan),
}

/// A missing observation is distinct from an observed empty preference.
#[derive(Debug)]
pub(crate) enum Observation<T> {
    Known(T),
    Unknown,
}

impl<T: Serialize> Serialize for Observation<T> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut value = serializer.serialize_struct(
            "Observation",
            if matches!(self, Self::Known(_)) { 2 } else { 1 },
        )?;
        value.serialize_field("known", &matches!(self, Self::Known(_)))?;
        if let Self::Known(observed) = self {
            value.serialize_field("value", observed)?;
        }
        value.end()
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum ChangeKind {
    Proposed,
    Confirmed,
}

#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
enum PreferenceResource {
    TargetPreference,
}

#[derive(Debug, Serialize)]
struct PreferenceField {
    field: &'static str,
    before: Observation<Option<String>>,
    after: Observation<Option<String>>,
}

/// One change to the local saved preference, independent of shell overrides.
#[derive(Debug, Serialize)]
pub(crate) struct PreferenceChange {
    kind: ChangeKind,
    resource: PreferenceResource,
    fields: [PreferenceField; 1],
}

impl PreferenceChange {
    fn new(kind: ChangeKind, before: Option<String>, after: Option<String>) -> Self {
        Self {
            kind,
            resource: PreferenceResource::TargetPreference,
            fields: [PreferenceField {
                field: "savedTarget",
                before: Observation::Known(before),
                after: Observation::Known(after),
            }],
        }
    }

    fn human(&self, styled: bool) -> String {
        let (before, after) = match self.kind {
            ChangeKind::Proposed => ("Current", "Proposed"),
            ChangeKind::Confirmed => ("Before", "Now"),
        };
        let field = &self.fields[0];
        let unchanged = matches!((&field.before, &field.after), (Observation::Known(before), Observation::Known(after)) if before == after);
        let mut before_value = preference_text(&field.before).to_owned();
        let mut after_value = preference_text(&field.after).to_owned();
        if styled
            && !unchanged
            && matches!(
                (&field.before, &field.after),
                (Observation::Known(_), Observation::Known(_))
            )
        {
            let old = anstyle::Style::new()
                .fg_color(Some(anstyle::AnsiColor::Red.into()))
                .strikethrough();
            let new = anstyle::Style::new().fg_color(Some(anstyle::AnsiColor::Green.into()));
            before_value = format!("{}{before_value}{}", old.render(), old.render_reset());
            after_value = format!("{}{after_value}{}", new.render(), new.render_reset());
        }
        format!(
            "{before} / {after}\nSaved target\n  {before}: {}\n  -> {after}: {}{}\n",
            before_value,
            after_value,
            if unchanged { " (unchanged)" } else { "" },
        )
    }
}

fn preference_text(observation: &Observation<Option<String>>) -> &str {
    match observation {
        Observation::Known(Some(label)) => label,
        Observation::Known(None) => "not selected",
        Observation::Unknown => "unknown",
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum OutgoingDataCategory {
    PublicApiIdentity,
    HttpRequestMetadata,
}

impl OutgoingDataCategory {
    fn human(&self) -> &'static str {
        match self {
            Self::PublicApiIdentity => "public API identity",
            Self::HttpRequestMetadata => "HTTP request metadata",
        }
    }
}

/// Planned recipients. Remote locations can remain unknown until discovery.
#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub(crate) enum Destination {
    LocalTargetRegistry,
    Api { url: Observation<String> },
    IssuerMetadata { url: Observation<String> },
    IssuerKeySet { url: Observation<String> },
    Proxy { url: Observation<String> },
}

impl Destination {
    fn human(&self) -> String {
        let (label, location) = match self {
            Self::LocalTargetRegistry => return "local target registry".to_owned(),
            Self::Api { url } => ("API identity", url),
            Self::IssuerMetadata { url } => ("issuer metadata", url),
            Self::IssuerKeySet { url } => ("issuer key set", url),
            Self::Proxy { url } => ("proxy", url),
        };
        match location {
            Observation::Known(url) => format!("{label}: {url}"),
            Observation::Unknown => format!("{label}: unknown"),
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum UnresolvedFact {
    RemoteIdentityUnverified,
    ProviderDestinationsUnresolved,
    PersistenceNotPerformed,
    EffectiveTargetUnresolved,
    RemoteHealthUnverified,
}

impl UnresolvedFact {
    fn human(&self) -> &'static str {
        match self {
            Self::RemoteIdentityUnverified => "remote identity unverified",
            Self::ProviderDestinationsUnresolved => "provider destinations unknown",
            Self::PersistenceNotPerformed => "save not performed",
            Self::EffectiveTargetUnresolved => "effective target unresolved",
            Self::RemoteHealthUnverified => "remote health unverified",
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct Plan {
    pub operation: &'static str,
    pub requested_target: Option<String>,
    pub api_url: Option<String>,
    pub effective_target: Option<String>,
    pub source: Option<SelectionSource>,
    pub intended_effects: Vec<&'static str>,
    pub checks_performed: Vec<&'static str>,
    pub remote_verification: &'static str,
    pub changes: Vec<PreferenceChange>,
    pub outgoing_data_categories: Vec<OutgoingDataCategory>,
    pub destinations: Vec<Destination>,
    pub unresolved_facts: Vec<UnresolvedFact>,
}

/// Preserve confirmed facts when persistence or final reporting is incomplete.
#[derive(Debug)]
pub(crate) struct Report {
    pub data: Option<Data>,
    pub error: Option<TargetError>,
    pub warnings: Vec<Warning>,
    pub exit: u8,
}

impl Report {
    fn observe_stop(mut self, code: u8) -> Self {
        if matches!(code, 130 | 143) {
            self.exit = code;
            self.error = Some(TargetError::Interrupted);
        }
        self
    }
    pub(super) fn success(data: Data) -> Self {
        Self {
            data: Some(data),
            error: None,
            warnings: vec![],
            exit: 0,
        }
    }
    pub(super) fn failure(error: TargetError) -> Self {
        let exit = if matches!(
            error,
            TargetError::InvalidLabel | TargetError::InvalidProxy | TargetError::InvalidApiUrl(_)
        ) {
            2
        } else {
            1
        };
        Self {
            data: None,
            error: Some(error),
            warnings: vec![],
            exit,
        }
    }

    pub(crate) fn human(&self, styled: bool) -> String {
        match &self.data {
            Some(Data::Registration {
                target,
                registration,
                ..
            }) => format!(
                "Target: {}\nRegistration: {registration}\nAPI: {}\nInstallation: {}\n",
                target.label, target.api_url, target.installation_id
            ),
            Some(Data::Selection {
                saved_target,
                effective_target,
                save_status,
                changes,
                ..
            }) => {
                let mut text = format!(
                    "Saved target: {}\nEffective target: {}\n",
                    saved_target.as_deref().unwrap_or("unconfirmed"),
                    effective_target.as_deref().unwrap_or("unresolved")
                );
                if *save_status == "unchanged" {
                    text.push_str("Preference unchanged.\n");
                }
                for change in changes {
                    text.push_str(&change.human(styled));
                }
                text
            }
            Some(Data::Inspection { target, source, .. }) => format!(
                "Target: {}\nAPI: {}\nIssuer: {}\nInstallation: {}\nSource: {source:?}\nVerification: saved binding\n",
                target.label, target.api_url, target.issuer_url, target.installation_id
            ),
            Some(Data::Plan(plan)) => {
                let mut text = format!("Dry-run: {}\n", plan.operation);
                if let Some(target) = &plan.requested_target {
                    let _ = writeln!(text, "Requested target: {target}");
                }
                if let Some(target) = &plan.effective_target {
                    let _ = writeln!(text, "Effective target: {target}");
                }
                if let Some(source) = plan.source {
                    let _ = writeln!(text, "Source: {source:?}");
                }
                if let Some(api) = &plan.api_url {
                    let _ = writeln!(text, "API: {api}");
                }
                let _ = writeln!(
                    text,
                    "Intended effects: {}\nRemote verification: not performed",
                    plan.intended_effects.join(", ")
                );
                for change in &plan.changes {
                    text.push_str(&change.human(styled));
                }
                let categories = plan
                    .outgoing_data_categories
                    .iter()
                    .map(OutgoingDataCategory::human)
                    .collect::<Vec<_>>();
                let _ = writeln!(
                    text,
                    "Outgoing network data: {}",
                    if categories.is_empty() {
                        "none".to_owned()
                    } else {
                        categories.join(", ")
                    }
                );
                text.push_str("Destinations:\n");
                for destination in &plan.destinations {
                    let _ = writeln!(text, "  {}", destination.human());
                }
                let _ = writeln!(
                    text,
                    "Unresolved: {}",
                    plan.unresolved_facts
                        .iter()
                        .map(UnresolvedFact::human)
                        .collect::<Vec<_>>()
                        .join(", ")
                );
                text
            }
            None => String::new(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capable_change_views_style_values_without_styling_their_meaning() {
        for (kind, before, after) in [
            (ChangeKind::Proposed, "Current", "Proposed"),
            (ChangeKind::Confirmed, "Before", "Now"),
        ] {
            let change = PreferenceChange::new(kind, Some("prod".into()), Some("dev".into()));
            assert_eq!(
                change.human(true),
                format!(
                    "{before} / {after}\nSaved target\n  {before}: \u{1b}[9m\u{1b}[31mprod\u{1b}[0m\n  -> {after}: \u{1b}[32mdev\u{1b}[0m\n"
                )
            );
            assert_eq!(
                change.human(false),
                format!("{before} / {after}\nSaved target\n  {before}: prod\n  -> {after}: dev\n")
            );
        }
    }

    #[test]
    fn unknown_and_identical_change_values_stay_neutral() {
        for (before, after, expected) in [
            (
                Observation::Known(Some("dev".into())),
                Observation::Known(Some("dev".into())),
                "Current: dev\n  -> Proposed: dev (unchanged)",
            ),
            (
                Observation::Known(None),
                Observation::Known(None),
                "Current: not selected\n  -> Proposed: not selected (unchanged)",
            ),
            (
                Observation::Unknown,
                Observation::Known(Some("dev".into())),
                "Current: unknown\n  -> Proposed: dev",
            ),
            (
                Observation::Known(Some("prod".into())),
                Observation::Unknown,
                "Current: prod\n  -> Proposed: unknown",
            ),
        ] {
            let change = PreferenceChange {
                kind: ChangeKind::Proposed,
                resource: PreferenceResource::TargetPreference,
                fields: [PreferenceField {
                    field: "savedTarget",
                    before,
                    after,
                }],
            };
            let text = change.human(true);
            assert!(!text.contains('\u{1b}'), "{text:?}");
            assert!(text.contains(expected), "{text}");
        }
    }

    #[test]
    fn unconfirmed_save_never_acquires_a_colored_completed_view() {
        let report = Report {
            data: Some(Data::Selection {
                requested_target: "dev".into(),
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
        assert_eq!(
            report.human(true),
            "Saved target: unconfirmed\nEffective target: unresolved\n"
        );
        assert_eq!(report.exit, 1);
        assert!(matches!(report.error, Some(TargetError::Uncertain)));
    }

    #[test]
    fn an_interrupt_after_confirmed_save_retains_the_saved_preference() {
        let report = Report::success(Data::Selection {
            requested_target: "dev".into(),
            saved_target: Some("dev".into()),
            effective_target: Some("dev".into()),
            source: Some(SelectionSource::Saved),
            save_status: "saved",
            changes: vec![PreferenceChange::new(
                ChangeKind::Confirmed,
                Some("prod".into()),
                Some("dev".into()),
            )],
        })
        .observe_stop(130);
        assert_eq!(report.exit, 130);
        assert!(matches!(report.error, Some(TargetError::Interrupted)));
        assert!(report.human(true).contains("Before / Now\nSaved target\n  Before: \u{1b}[9m\u{1b}[31mprod\u{1b}[0m\n  -> Now: \u{1b}[32mdev\u{1b}[0m\n"));
        assert!(
            matches!(report.data, Some(Data::Selection { saved_target: Some(label), save_status: "saved", .. }) if label == "dev")
        );
    }
}

/// Keep signal observation alive until the final stdout/stderr operation finishes.
#[derive(Debug)]
pub(crate) struct Execution {
    pub report: Report,
    _signals: Option<SignalLifetime>,
}

impl From<Report> for Execution {
    fn from(report: Report) -> Self {
        Self {
            report,
            _signals: None,
        }
    }
}

#[derive(Debug)]
struct SignalLifetime {
    runtime: tokio::runtime::Runtime,
    observer: tokio::task::JoinHandle<()>,
}

impl Drop for SignalLifetime {
    fn drop(&mut self) {
        self.observer.abort();
        self.runtime.block_on(async {
            let _ = (&mut self.observer).await;
        });
    }
}

/// Initialize runtime only for the selected target command, after static help has exited.
pub(crate) fn run(
    arguments: Arguments,
    explicit: Option<&str>,
    dry_run: bool,
    stderr: &mut impl Write,
) -> Execution {
    let store = match Store::from_environment() {
        Ok(store) => store,
        Err(error) => return Report::failure(error).into(),
    };
    if dry_run {
        let planned = match arguments.command {
            Command::Add(arguments) => add::plan(arguments, &store).map(Report::success),
            Command::Use(arguments) => use_target::plan(arguments, &store),
            Command::Show => show::plan(&store, explicit).map(Report::success),
        };
        return match planned {
            Ok(report) => report,
            Err(error) => Report::failure(error),
        }
        .into();
    }
    // The runtime's one worker can observe signals while the caller finishes an
    // already-started synchronous atomic filesystem publication.
    let Ok(runtime) = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(1)
        .enable_all()
        .build()
    else {
        return Report::failure(TargetError::Io).into();
    };
    let stop = Arc::new(AtomicU8::new(0));
    let signal_state = stop.clone();
    let output_started = Arc::new(AtomicBool::new(false));
    let phase = output_started.clone();
    let setup = {
        let _entered = runtime.enter();
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt()).and_then(
            |interrupt| {
                tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                    .map(|terminate| (interrupt, terminate))
            },
        )
    };
    let Ok((mut interrupt, mut terminate)) = setup else {
        return Report::failure(TargetError::Io).into();
    };
    let (notification, mut receipt) = tokio::sync::oneshot::channel();
    let observer = runtime.spawn(async move {
        let code = tokio::select! { _ = interrupt.recv() => 130, _ = terminate.recv() => 143 };
        let final_output = phase.load(Ordering::Acquire);
        signal_state.store(code, Ordering::Release);
        if final_output {
            // The operation is finished. A blocked output pipe must not prevent
            // signal exit. The final record can be incomplete, with saved effects retained.
            std::process::exit(i32::from(code));
        }
        let _ = notification.send(code);
        if code == 130 {
            // A second INT has the accepted immediate process-exit meaning.
            interrupt.recv().await;
            std::process::exit(130);
        }
    });
    let mut explained = false;
    let report = runtime.block_on(async {
        let mut operation = Box::pin(async {
            match arguments.command {
                Command::Add(arguments) => add::execute(arguments, &store, &stop).await,
                Command::Use(arguments) => use_target::execute(arguments, &store, &stop).await,
                Command::Show => match show::execute(&store, explicit) { Ok(data) => Report::success(data), Err(error) => Report::failure(error) },
            }
        });
        tokio::select! {
            biased;
            signal = &mut receipt => {
                if matches!(signal, Ok(130)) {
                    let _ = writeln!(stderr, "Interruption started. A second INT exits immediately. No backend cancellation was requested.");
                    explained = true;
                }
                Report::failure(TargetError::Interrupted)
            }
            report = &mut operation => report,
        }
    });
    output_started.store(true, Ordering::Release);
    let code = stop.load(Ordering::Acquire);
    if code == 130 && !explained {
        let _ = writeln!(
            stderr,
            "Interruption started. A second INT exits immediately. No backend cancellation was requested."
        );
    }
    Execution {
        report: report.observe_stop(code),
        _signals: Some(SignalLifetime { runtime, observer }),
    }
}
