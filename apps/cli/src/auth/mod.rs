//! Transient human authorization shared by maintained operator examples.

pub mod callback;

pub mod recipient_proof;

pub mod maintenance_handoff;

pub mod flow;

mod transport;

use clap::{Args, Parser, ValueEnum};
use serde::Serialize;
use std::{
    ffi::OsString,
    io::{Read as _, Write as _},
    path::{Path, PathBuf},
    process::ExitCode,
    sync::atomic::{AtomicU8, Ordering},
};
use zeroize::Zeroizing;

use self::{
    flow::{BootstrapOutcome, BrowserLauncher, HostContext, RepairOutcome, bootstrap, repair},
    maintenance_handoff::{
        CleanupStatus, ExecutionSpec, MaintenanceEffect, NativeBrowserBridge,
        PRIVATE_BROWSER_LAUNCH_ARGUMENT, SystemBrowser, run_system_browser_child,
    },
    recipient_proof::RepairRequest,
};

#[derive(Args)]
pub(crate) struct InputArguments {
    /// Trusted installation, recipient and TLS context supplied by host setup.
    #[arg(long, value_name = "FILE")]
    pub(crate) host_context: PathBuf,
    /// Reviewed proof-free request for the selected host-maintenance operation.
    #[arg(long, value_name = "FILE")]
    pub(crate) request: PathBuf,
    /// Trusted direct argv descriptor for the existing host maintenance transport.
    #[arg(long, value_name = "FILE")]
    pub(crate) exec_spec: PathBuf,
}
#[derive(Parser)]
#[command(about = "Acquire fresh browser proof for reviewed stranded Project metadata repair")]
struct OperatorArguments {
    #[command(flatten)]
    input: InputArguments,
}
#[derive(Parser)]
#[command(about = "Qualification-only adapter for the shared transient recipient-proof owner")]
struct DriverArguments {
    #[command(flatten)]
    input: InputArguments,
    /// Absent socket under a fresh fixture-owned 0700 parent, in the same UID/network namespace.
    #[arg(long, value_name = "ABSOLUTE_SOCKET")]
    browser_bridge: PathBuf,
    /// Select the existing maintenance input contract for this qualification adapter.
    #[arg(long, value_enum, default_value = "repair-stranded-authority")]
    mode: DriverMode,
}

#[derive(Clone, Copy, ValueEnum)]
enum DriverMode {
    RepairStrandedAuthority,
    BootstrapFirstAdministrator,
}

/// Run the maintained repair-only example, including its exact private launcher dispatch.
///
/// The main CLI has no new command or token-output mode. This entry point saves
/// no login and requires an already-admitted human plus independently trusted
/// host context and maintenance execution intent.
#[must_use]
pub fn operator_example_main() -> ExitCode {
    let arguments: Vec<OsString> = std::env::args_os().collect();
    if arguments.len() == 2 && arguments[1] == PRIVATE_BROWSER_LAUNCH_ARGUMENT {
        return if run_system_browser_child().is_ok() {
            ExitCode::SUCCESS
        } else {
            ExitCode::from(1)
        };
    }
    let arguments = match parse_example::<OperatorArguments>(arguments) {
        Ok(arguments) => arguments,
        Err(exit) => return exit,
    };
    let Ok(prepared) = prepare(&arguments.input) else {
        return invalid_input();
    };
    let Ok(browser) = SystemBrowser::current_process() else {
        return startup_failure();
    };
    run_example(&prepared, browser)
}

/// Run the private qualification adapter through the same production operation.
///
/// Sends only one bounded flow-sensitive navigation event through protected
/// same-UID IPC. It never accepts claims, callbacks or replacement endpoints.
#[must_use]
pub fn native_driver_main() -> ExitCode {
    let arguments = match parse_example::<DriverArguments>(std::env::args_os()) {
        Ok(arguments) => arguments,
        Err(exit) => return exit,
    };
    if !arguments.browser_bridge.is_absolute() {
        return invalid_input();
    }
    if matches!(arguments.mode, DriverMode::BootstrapFirstAdministrator) {
        let execution = bootstrap_command(
            &arguments.input,
            None,
            false,
            || Ok(NativeBrowserBridge::new(arguments.browser_bridge)),
            &mut std::io::stderr().lock(),
        );
        return crate::app::report_native_bootstrap(&execution);
    }
    let Ok(prepared) = prepare(&arguments.input) else {
        return invalid_input();
    };
    run_example(
        &prepared,
        NativeBrowserBridge::new(arguments.browser_bridge),
    )
}

fn parse_example<T: Parser>(arguments: impl IntoIterator<Item = OsString>) -> Result<T, ExitCode> {
    T::try_parse_from(arguments).map_err(|error| match error.kind() {
        clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion => {
            if error.print().is_ok() {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            }
        }
        _ => {
            eprintln!("Invalid helper arguments. Use --help.");
            ExitCode::from(2)
        }
    })
}

/// Hold complete input snapshots before any provider, browser or maintenance effect.
struct PreparedInvocation {
    host: HostContext,
    request: Zeroizing<Vec<u8>>,
    execution: ExecutionSpec,
}
fn prepare(arguments: &InputArguments) -> Result<PreparedInvocation, ()> {
    let request = read_operator_file(&arguments.request)?;
    RepairRequest::parse(&request).map_err(|_| ())?;
    let host = HostContext::parse(&read_operator_file(&arguments.host_context)?).map_err(|_| ())?;
    let execution =
        ExecutionSpec::parse(&read_operator_file(&arguments.exec_spec)?).map_err(|_| ())?;
    Ok(PreparedInvocation {
        host,
        request,
        execution,
    })
}
fn read_operator_file(path: &Path) -> Result<Zeroizing<Vec<u8>>, ()> {
    use std::os::unix::fs::OpenOptionsExt as _;
    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(nix::libc::O_NOFOLLOW | nix::libc::O_NONBLOCK)
        .open(path)
        .map_err(|_| ())?;
    let metadata = file.metadata().map_err(|_| ())?;
    if !metadata.is_file() || metadata.len() > 65_536 {
        return Err(());
    }
    let mut bytes = Zeroizing::new(Vec::new());
    file.take(65_537).read_to_end(&mut bytes).map_err(|_| ())?;
    if bytes.len() > 65_536 {
        return Err(());
    }
    Ok(bytes)
}

/// Reuse the existing signal owner without changing its second-INT or finalization policy.
fn run_cancellable<T, F, Fut>(
    operation: F,
    diagnostics: &mut impl std::io::Write,
) -> Result<(T, u8), ()>
where
    F: FnOnce(tokio::sync::oneshot::Receiver<()>) -> Fut,
    Fut: std::future::Future<Output = T>,
{
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|_| ())?;
    runtime.block_on(async {
        let Ok(mut interrupt)=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt()) else {return Err(());};
        let Ok(mut terminate)=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) else {return Err(());};
        let (cancelling,cancelled)=tokio::sync::oneshot::channel();
        let exit=AtomicU8::new(0);
        let mut operation=std::pin::pin!(operation(cancelled));
        let mut monitor=std::pin::pin!(async {
            let mut cancelling=Some(cancelling);
            let mut interrupts=0;
            loop {
                tokio::select! {
                    signal=interrupt.recv()=>{
                        if signal.is_none() {exit.store(1,Ordering::Relaxed);if let Some(cancelling)=cancelling.take() {let _=cancelling.send(());}return;}
                        interrupts+=1;
                        if interrupts>1 {
                            // The accepted second-INT rule forces exit without a cleanup
                            // receipt. The original maintenance outcome may be unknown.
                            std::process::exit(130);
                        }
                        exit.store(130,Ordering::Relaxed);
                        let _=writeln!(diagnostics,"Interrupted. Finishing bounded local cleanup. A second Ctrl-C exits immediately.");
                        if let Some(cancelling)=cancelling.take() {let _=cancelling.send(());}
                    },
                    signal=terminate.recv()=>{
                        exit.store(if signal.is_some() {143}else{1},Ordering::Relaxed);
                        if let Some(cancelling)=cancelling.take() {let _=cancelling.send(());}
                        if signal.is_none() {return;}
                    },
                }
            }
        });
        let result=tokio::select! {biased;()=&mut monitor=>operation.await,result=&mut operation=>result};
        Ok((result, exit.load(Ordering::Relaxed)))
    })
}

fn run_example(prepared: &PreparedInvocation, mut browser: impl BrowserLauncher) -> ExitCode {
    let Ok((result, interrupted)) = run_cancellable(
        |cancelled| {
            repair(
                &prepared.host,
                &prepared.request,
                &prepared.execution,
                &mut browser,
                async {
                    let _ = cancelled.await;
                },
            )
        },
        &mut std::io::stderr().lock(),
    ) else {
        return startup_failure();
    };
    let (value, ordinary_exit) = match result {
        Ok(result) => {
            let success = fully_confirmed(&result);
            let _ = write_diagnostics(&result, &mut std::io::stderr().lock());
            (
                serde_json::json!({"schemaVersion":1,"result":result}),
                u8::from(!success),
            )
        }
        Err(error) => {
            let usage = matches!(
                error.kind,
                flow::FailureKind::InvalidRequest | flow::FailureKind::InvalidContext
            );
            (
                serde_json::json!({"schemaVersion":1,"error":error}),
                if usage { 2 } else { 1 },
            )
        }
    };
    if !emit_json(&value) {
        return ExitCode::from(1);
    }
    ExitCode::from(if interrupted == 0 {
        ordinary_exit
    } else {
        interrupted
    })
}

/// One safe command result is shared by the public and native adapters.
#[derive(Debug)]
pub(crate) struct BootstrapExecution {
    pub data: Option<BootstrapData>,
    pub error: Option<BootstrapError>,
    pub exit: u8,
    pub human: String,
}

#[derive(Debug, Serialize)]
#[serde(untagged)]
pub(crate) enum BootstrapData {
    Plan(Box<BootstrapPlan>),
    Observation(BootstrapOutcome),
    ProofFailure(flow::RepairFailure),
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct BootstrapPlan {
    operation: &'static str,
    provided_installation_id: uuid::Uuid,
    provided_identity_id: uuid::Uuid,
    original_operation_id: String,
    provided_access_revision: i64,
    checks_performed: [&'static str; 3],
    intended_effects: [&'static str; 3],
    backend_verification: &'static str,
    credential_persistence: &'static str,
    destinations: flow::BootstrapDestinations,
    outgoing_data_categories: [BootstrapOutgoingData; 4],
}

/// Bootstrap-specific data categories do not disclose input contents or credentials.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
enum BootstrapOutgoingData {
    PublicApiAndHttpMetadata,
    OAuthTransaction,
    TransientCredentials,
    ReviewedHostRequest,
}

#[derive(Debug, Clone, Copy)]
pub(crate) enum BootstrapError {
    Input,
    TargetConflict,
    InteractionRequired,
    Startup,
    Proof,
    Operation,
    Unconfirmed,
    Interrupted,
}

impl BootstrapError {
    pub(crate) fn code(self) -> &'static str {
        match self {
            Self::Input => "invalid_bootstrap_input",
            Self::TargetConflict => "conflicting_target",
            Self::InteractionRequired => "interaction_required",
            Self::Startup => "startup_unavailable",
            Self::Proof => "bootstrap_proof_failed",
            Self::Operation => "bootstrap_failed",
            Self::Unconfirmed => "bootstrap_unconfirmed",
            Self::Interrupted => "interrupted",
        }
    }
    pub(crate) fn message(self) -> &'static str {
        match self {
            Self::Input => {
                "Supply three valid bounded host-controlled files with matching installation and identity bindings."
            }
            Self::TargetConflict => "Host-context bootstrap cannot be combined with --target.",
            Self::InteractionRequired => {
                "Browser proof requires interactive input without --no-input. Use --dry-run to inspect the request without starting a human flow."
            }
            Self::Startup => "The bounded browser-proof operation could not start.",
            Self::Proof => "Fresh same-person browser proof could not be established.",
            Self::Operation => "The requested host claim did not complete successfully.",
            Self::Unconfirmed => {
                "The original claim or its cleanup is unconfirmed. Recover only with the exact original request and fresh same-person proof."
            }
            Self::Interrupted => {
                "The operation was interrupted. Preserve the original request and inspect the reported claim and cleanup facts."
            }
        }
    }
}

/// Freeze inputs before the only browser/claim handler shared by both adapters.
pub(crate) fn bootstrap_command<B: BrowserLauncher>(
    arguments: &InputArguments,
    explicit_target: Option<&str>,
    dry_run: bool,
    browser: impl FnOnce() -> Result<B, flow::BrowserLaunchError>,
    diagnostics: &mut impl std::io::Write,
) -> BootstrapExecution {
    let failed = |error: BootstrapError, exit| BootstrapExecution {
        data: None,
        error: Some(error),
        exit,
        human: String::new(),
    };
    if explicit_target.is_some() {
        return failed(BootstrapError::TargetConflict, 2);
    }
    let prepared = prepare_bootstrap(arguments);
    let Ok(prepared) = prepared else {
        return failed(BootstrapError::Input, 2);
    };
    if dry_run {
        return plan_bootstrap(&prepared).unwrap_or_else(|()| failed(BootstrapError::Input, 2));
    }
    let Ok(mut browser) = browser() else {
        return failed(BootstrapError::Startup, 1);
    };
    let Ok((result, interrupted)) = run_cancellable(
        |cancelled| {
            bootstrap(
                &prepared.host,
                &prepared.request,
                &prepared.execution,
                &mut browser,
                true,
                async {
                    let _ = cancelled.await;
                },
            )
        },
        diagnostics,
    ) else {
        return failed(BootstrapError::Startup, 1);
    };
    let mut execution = match result {
        Ok(result) => bootstrap_observation(result),
        Err(error) => bootstrap_proof_failure(error),
    };
    if interrupted != 0 {
        execution.exit = interrupted;
        execution.error = Some(BootstrapError::Interrupted);
    }
    execution
}

/// Keep original claim and cleanup facts together at the existing result boundary.
fn bootstrap_observation(result: BootstrapOutcome) -> BootstrapExecution {
    let committed = matches!(
        result.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    );
    let confirmed = committed
        && result.maintenance.failure.is_none()
        && result.maintenance.process_cleanup == CleanupStatus::Confirmed
        && result.credential_cleanup == CleanupStatus::Confirmed;
    let uncertain =
        matches!(result.maintenance.effect, MaintenanceEffect::Unknown { .. }) || committed;
    let session = match result.current_session {
        flow::SessionObservation::Admitted { principal_id } => {
            format!("admitted principal {principal_id}")
        }
        flow::SessionObservation::Unavailable => "not established".to_owned(),
        flow::SessionObservation::NotRequested => "not requested".to_owned(),
    };
    let failure = result
        .maintenance
        .failure
        .map_or_else(|| "none".to_owned(), |failure| format!("{failure:?}"));
    let backend = result
        .maintenance
        .backend_error
        .map_or_else(|| "unavailable".to_owned(), |code| code.to_string());
    let human = format!(
        "Original claim: {}.\nCurrent API session: {}.\nMaintenance failure: {}. Backend classification: {}.\nProcess cleanup: {:?}. New credential cleanup: {:?}.\nNo login was saved. {}\n",
        if committed {
            "confirmed"
        } else if uncertain {
            "unknown"
        } else {
            "unestablished. This invocation did not dispatch a host claim. Any earlier original outcome is unestablished"
        },
        session,
        failure,
        backend,
        result.maintenance.process_cleanup,
        result.credential_cleanup,
        if confirmed {
            "Current admission is a separate observation."
        } else {
            "Recover only with the exact original request and fresh same-person proof. No automatic retry was sent."
        }
    );
    BootstrapExecution {
        data: Some(BootstrapData::Observation(result)),
        error: if confirmed {
            None
        } else if uncertain {
            Some(BootstrapError::Unconfirmed)
        } else {
            Some(BootstrapError::Operation)
        },
        exit: u8::from(!confirmed),
        human,
    }
}

/// Preserve the existing typed proof failure for human and machine reporting.
fn bootstrap_proof_failure(error: flow::RepairFailure) -> BootstrapExecution {
    let human = format!(
        "Proof failure stage: {:?}.\nResource cleanup: {:?}. New credential cleanup: {:?}.\nThis invocation did not dispatch a host claim. Any earlier original outcome is unchanged. No login was saved.\nConfirm reported cleanup before recovering with the exact original request and fresh same-person proof.\n",
        error.kind, error.resource_cleanup, error.credential_cleanup
    );
    BootstrapExecution {
        data: Some(BootstrapData::ProofFailure(error)),
        error: Some(BootstrapError::Proof),
        exit: 1,
        human,
    }
}

/// Read each bounded file once and bind its exact contents before dispatch.
fn prepare_bootstrap(arguments: &InputArguments) -> Result<PreparedInvocation, ()> {
    let request = read_operator_file(&arguments.request)?;
    let host = HostContext::parse(&read_operator_file(&arguments.host_context)?).map_err(|_| ())?;
    host.bound_bootstrap_request(&request).map_err(|_| ())?;
    host.bootstrap_destinations().map_err(|_| ())?;
    let execution =
        ExecutionSpec::parse(&read_operator_file(&arguments.exec_spec)?).map_err(|_| ())?;
    Ok(PreparedInvocation {
        host,
        request,
        execution,
    })
}

/// Explain validated local input without treating it as current backend authority.
fn plan_bootstrap(prepared: &PreparedInvocation) -> Result<BootstrapExecution, ()> {
    let request = prepared
        .host
        .bound_bootstrap_request(&prepared.request)
        .map_err(|_| ())?;
    let destinations = prepared.host.bootstrap_destinations().map_err(|_| ())?;
    Ok(BootstrapExecution {
        human: format!(
            "Would acquire fresh same-person browser proof and submit the original host claim once.\nProvided installation: {}\nProvided identity: {}\nOriginal operation: {:?}\nProvided API: {}\nProvided issuer: {}\nProxy: {}\nHost execution: operator-controlled-unverified. Provider endpoint paths are unresolved until discovery.\nOutgoing data categories: public API identity and HTTP metadata, OAuth transaction data, transient credentials, reviewed host request.\nBackend eligibility and current admission are unverified. No browser, credential or host command was dispatched. No login is saved.\n",
            request.expected_installation_id,
            request.expected_identity_id,
            request.operation_id,
            destinations.api,
            destinations.issuer,
            destinations.proxy.as_deref().unwrap_or("none provided")
        ),
        data: Some(BootstrapData::Plan(Box::new(BootstrapPlan {
            operation: "bootstrap-first-administrator",
            provided_installation_id: request.expected_installation_id,
            provided_identity_id: request.expected_identity_id,
            original_operation_id: request.operation_id,
            provided_access_revision: request.expected_access_revision,
            checks_performed: [
                "bounded-regular-input-files",
                "strict-input-contracts",
                "matching-provided-bindings",
            ],
            intended_effects: [
                "fresh-browser-proof",
                "one-protected-host-claim",
                "new-credential-revocation",
            ],
            backend_verification: "not-performed",
            credential_persistence: "none",
            destinations,
            outgoing_data_categories: [
                BootstrapOutgoingData::PublicApiAndHttpMetadata,
                BootstrapOutgoingData::OAuthTransaction,
                BootstrapOutgoingData::TransientCredentials,
                BootstrapOutgoingData::ReviewedHostRequest,
            ],
        }))),
        error: None,
        exit: 0,
    })
}

fn fully_confirmed(outcome: &RepairOutcome) -> bool {
    matches!(
        outcome.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    ) && outcome.maintenance.process_cleanup == CleanupStatus::Confirmed
        && outcome.maintenance.failure.is_none()
        && outcome.credential_cleanup == CleanupStatus::Confirmed
}
/// Observe only fixed fields at the existing reporting boundary.
fn write_diagnostics(
    outcome: &RepairOutcome,
    output: &mut impl std::io::Write,
) -> std::io::Result<()> {
    if fully_confirmed(outcome)
        || matches!(outcome.maintenance.effect, MaintenanceEffect::NotStarted)
    {
        return Ok(());
    }
    let reply = if let Some(code) = outcome.maintenance.backend_error {
        code.to_string()
    } else if matches!(
        outcome.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    ) {
        "receipt".into()
    } else {
        "unavailable".into()
    };
    // Closed spellings and u8 statuses bound both lines below 512 bytes.
    // A diagnostic writer failure cannot replace the original result.
    writeln!(
        output,
        "recipient-proof: maintenance child={} reply={reply}",
        outcome.maintenance.child_status
    )?;
    writeln!(
        output,
        "recipient-proof: revocation access={} refresh={}",
        outcome.credential_observations.access, outcome.credential_observations.refresh
    )
}
fn emit_json(value: &serde_json::Value) -> bool {
    let mut output = std::io::stdout().lock();
    if serde_json::to_writer(&mut output, value).is_err() || output.write_all(b"\n").is_err() {
        eprintln!(
            "The helper result could not be written. Inspect the original operation before repeating it."
        );
        return false;
    }
    true
}
fn invalid_input() -> ExitCode {
    let _ = emit_json(&serde_json::json!({"schemaVersion":1,"error":{"kind":"invalid-input"}}));
    ExitCode::from(2)
}
fn startup_failure() -> ExitCode {
    let _ =
        emit_json(&serde_json::json!({"schemaVersion":1,"error":{"kind":"startup-unavailable"}}));
    ExitCode::from(1)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::flow::{CredentialObservations, RevocationObservation};
    use super::maintenance_handoff::{ChildStatus, HandoffFailure, HandoffOutcome};
    use super::recipient_proof::MaintenanceErrorCode;
    use super::*;

    fn failed_outcome() -> RepairOutcome {
        RepairOutcome {
            maintenance: HandoffOutcome {
                effect: MaintenanceEffect::Unknown {
                    operation_id: "protected-operation-sentinel".into(),
                },
                process_cleanup: CleanupStatus::Confirmed,
                failure: Some(HandoffFailure::Exit),
                child_status: ChildStatus::Exited(7),
                backend_error: Some(MaintenanceErrorCode::StaleRevision),
            },
            credential_cleanup: CleanupStatus::Unconfirmed,
            credential_observations: CredentialObservations {
                access: RevocationObservation::ProviderRejected,
                refresh: RevocationObservation::NotIssued,
            },
        }
    }

    #[test]
    fn recipient_diagnostic_outer_adapter_emits_only_two_bounded_fixed_lines() {
        let result = failed_outcome();
        let mut output = Vec::new();
        write_diagnostics(&result, &mut output).unwrap();
        assert!(output.len() <= 512);
        let text = String::from_utf8(output).unwrap();
        assert_eq!(text.lines().count(), 2);
        assert!(text.contains("child=exit-7 reply=stale_revision"));
        assert!(text.contains("access=provider-rejected refresh=not-issued"));
        assert!(!text.contains("protected-operation-sentinel"));
        let json = serde_json::to_value(&result).unwrap();
        assert_eq!(json.as_object().unwrap().len(), 2);
        assert_eq!(json["maintenance"].as_object().unwrap().len(), 3);
    }

    #[test]
    fn recipient_diagnostic_outer_adapter_suppresses_unlaunched_and_successful_results() {
        let mut result = failed_outcome();
        result.maintenance.effect = MaintenanceEffect::NotStarted;
        let mut output = Vec::new();
        write_diagnostics(&result, &mut output).unwrap();
        assert!(output.is_empty());
        let receipt = serde_json::from_value(serde_json::json!({
            "schemaVersion":1,"mode":"repair-stranded-authority","operationId":"original-operation",
            "installationId":"00000000-0000-0000-0000-000000000001",
            "principalId":"00000000-0000-0000-0000-00000000000a","accessRevision":5,"outcome":"repaired",
            "responsibility":{"kind":"action-grantor","target":{"kind":"project","projectId":"00000000-0000-0000-0000-000000000003"},"actionId":"edit-project-metadata"}
        })).unwrap();
        result.maintenance.effect = MaintenanceEffect::Committed {
            receipt: Box::new(receipt),
        };
        result.maintenance.failure = None;
        result.credential_cleanup = CleanupStatus::Confirmed;
        write_diagnostics(&result, &mut output).unwrap();
        assert!(output.is_empty());
    }

    #[test]
    fn bootstrap_human_proof_failure_preserves_stage_and_both_cleanup_obligations() {
        let execution = bootstrap_proof_failure(flow::RepairFailure {
            kind: flow::FailureKind::Exchange,
            resource_cleanup: CleanupStatus::Unconfirmed,
            credential_cleanup: CleanupStatus::Unconfirmed,
        });
        assert_eq!(execution.exit, 1);
        assert!(execution.human.contains("Exchange"));
        assert!(execution.human.contains("Resource cleanup: Unconfirmed"));
        assert!(
            execution
                .human
                .contains("New credential cleanup: Unconfirmed")
        );
        assert!(execution.human.contains("did not dispatch a host claim"));
        assert!(execution.human.contains("No login was saved"));
    }

    #[test]
    fn bootstrap_human_maintenance_failures_keep_unknown_claim_and_closed_codes() {
        for (code, label) in [
            (
                MaintenanceErrorCode::AlreadyBootstrapped,
                "already_bootstrapped",
            ),
            (
                MaintenanceErrorCode::IdempotencyKeyReused,
                "idempotency_key_reused",
            ),
        ] {
            let execution = bootstrap_observation(BootstrapOutcome {
                maintenance: HandoffOutcome {
                    effect: MaintenanceEffect::Unknown {
                        operation_id: "protected-operation-sentinel".into(),
                    },
                    process_cleanup: CleanupStatus::Confirmed,
                    failure: Some(HandoffFailure::Exit),
                    child_status: ChildStatus::Exited(2),
                    backend_error: Some(code),
                },
                current_session: flow::SessionObservation::Unavailable,
                credential_cleanup: CleanupStatus::Unconfirmed,
                credential_observations: failed_outcome().credential_observations,
            });
            assert!(execution.human.contains("Original claim: unknown"));
            assert!(execution.human.contains("Maintenance failure: Exit"));
            assert!(execution.human.contains(label));
            let projected = serde_json::to_value(execution.data.as_ref().unwrap()).unwrap();
            assert_eq!(projected["consumerErrorCode"], label);
            assert_eq!(projected["maintenance"]["effect"]["status"], "unknown");
            assert!(
                execution
                    .human
                    .contains("New credential cleanup: Unconfirmed")
            );
            assert!(!execution.human.contains("did not dispatch"));
            assert!(!execution.human.contains("protected-operation-sentinel"));
        }
        let launch = bootstrap_observation(BootstrapOutcome {
            maintenance: HandoffOutcome {
                effect: MaintenanceEffect::NotStarted,
                process_cleanup: CleanupStatus::NotNeeded,
                failure: Some(HandoffFailure::Launch),
                child_status: ChildStatus::Unobserved,
                backend_error: None,
            },
            current_session: flow::SessionObservation::NotRequested,
            credential_cleanup: CleanupStatus::Confirmed,
            credential_observations: failed_outcome().credential_observations,
        });
        assert!(
            launch
                .human
                .contains("This invocation did not dispatch a host claim")
        );
        assert!(
            launch
                .human
                .contains("Any earlier original outcome is unestablished")
        );
        assert!(!launch.human.contains("Original claim: not started"));
        assert!(launch.human.contains("Maintenance failure: Launch"));
        assert_eq!(launch.exit, 1);
    }
}
