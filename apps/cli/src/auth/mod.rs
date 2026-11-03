//! Transient human authorization shared by maintained operator examples.

pub mod callback;

pub mod recipient_proof;

pub mod maintenance_handoff;

pub mod flow;

mod transport;

use clap::{Args, Parser};
use std::{
    ffi::OsString,
    io::{Read as _, Write as _},
    path::{Path, PathBuf},
    process::ExitCode,
    sync::atomic::{AtomicU8, Ordering},
};
use zeroize::Zeroizing;

use self::{
    flow::{BrowserLauncher, HostContext, RepairOutcome, repair},
    maintenance_handoff::{
        CleanupStatus, ExecutionSpec, MaintenanceEffect, NativeBrowserBridge,
        PRIVATE_BROWSER_LAUNCH_ARGUMENT, SystemBrowser, run_system_browser_child,
    },
    recipient_proof::RepairRequest,
};

#[derive(Args)]
struct InputArguments {
    /// Trusted installation, recipient and TLS context supplied by host setup.
    #[arg(long, value_name = "FILE")]
    host_context: PathBuf,
    /// Reviewed proof-free repair request. Bootstrap and supplied tokens are rejected.
    #[arg(long, value_name = "FILE")]
    request: PathBuf,
    /// Trusted direct argv descriptor for the existing host maintenance transport.
    #[arg(long, value_name = "FILE")]
    exec_spec: PathBuf,
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
    let Ok(prepared) = prepare(&arguments.input) else {
        return invalid_input();
    };
    if !arguments.browser_bridge.is_absolute() {
        return invalid_input();
    }
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

fn run_example(prepared: &PreparedInvocation, mut browser: impl BrowserLauncher) -> ExitCode {
    let Ok(runtime) = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
    else {
        return startup_failure();
    };
    runtime.block_on(async {
        let Ok(mut interrupt)=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt()) else {return startup_failure();};
        let Ok(mut terminate)=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) else {return startup_failure();};
        let (cancelling,cancelled)=tokio::sync::oneshot::channel();
        let exit=AtomicU8::new(0);
        let mut operation=std::pin::pin!(repair(&prepared.host,&prepared.request,&prepared.execution,&mut browser,async {let _=cancelled.await;}));
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
                        eprintln!("Interrupted. Finishing bounded local cleanup. A second Ctrl-C exits immediately.");
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
        let (value,ordinary_exit)=match result {
            Ok(result)=>{
                let success=fully_confirmed(&result);
                let _ = write_diagnostics(&result, &mut std::io::stderr().lock());
                (serde_json::json!({"schemaVersion":1,"result":result}),u8::from(!success))
            },
            Err(error)=>{
                let usage=matches!(error.kind,flow::FailureKind::InvalidRequest|flow::FailureKind::InvalidContext);
                (serde_json::json!({"schemaVersion":1,"error":error}),if usage {2}else{1})
            },
        };
        if !emit_json(&value) {return ExitCode::from(1);}
        let interrupted=exit.load(Ordering::Relaxed);
        ExitCode::from(if interrupted==0 {ordinary_exit}else{interrupted})
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
}
