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
use serde::Serialize;
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
    },
    Inspection {
        target: Target,
        source: SelectionSource,
        verification: &'static str,
    },
    Plan(Plan),
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

    pub(crate) fn human(&self) -> String {
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
                ..
            }) => format!(
                "Saved target: {}\nEffective target: {}\n",
                saved_target.as_deref().unwrap_or("unconfirmed"),
                effective_target.as_deref().unwrap_or("unresolved")
            ),
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
    fn an_interrupt_after_confirmed_save_retains_the_saved_preference() {
        let report = Report::success(Data::Selection {
            requested_target: "dev".into(),
            saved_target: Some("dev".into()),
            effective_target: Some("dev".into()),
            source: Some(SelectionSource::Saved),
            save_status: "saved",
        })
        .observe_stop(130);
        assert_eq!(report.exit, 130);
        assert!(matches!(report.error, Some(TargetError::Interrupted)));
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
            Command::Add(arguments) => add::plan(arguments, &store),
            Command::Use(arguments) => use_target::plan(arguments, &store),
            Command::Show => show::plan(&store, explicit),
        };
        return match planned {
            Ok(data) => Report::success(data),
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
