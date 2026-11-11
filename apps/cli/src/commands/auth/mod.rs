//! Declare explicit host-context authentication operations.

use clap::{Args, Subcommand};
use std::path::PathBuf;

#[derive(Debug, Args)]
pub(crate) struct Arguments {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub(crate) enum Command {
    /// Acquire fresh browser proof and claim the first administrator through host stdin
    BootstrapFirstAdministrator(BootstrapArguments),
}

#[derive(Debug, Args)]
pub(crate) struct BootstrapArguments {
    /// Trusted installation, expected person and TLS context from host setup.
    #[arg(long, value_name = "FILE")]
    pub host_context: PathBuf,
    /// Original proof-free first-administrator request with Access revision zero.
    #[arg(long, value_name = "FILE")]
    pub request: PathBuf,
    /// Trusted direct execution descriptor for the installed maintenance consumer.
    #[arg(long, value_name = "FILE")]
    pub exec_spec: PathBuf,
}

pub(crate) fn run(
    arguments: Arguments,
    target: Option<&str>,
    dry_run: bool,
    interaction_allowed: bool,
    diagnostics: &mut impl std::io::Write,
) -> crate::auth::BootstrapExecution {
    if target.is_none() && !dry_run && !interaction_allowed {
        return crate::auth::BootstrapExecution {
            data: None,
            error: Some(crate::auth::BootstrapError::InteractionRequired),
            exit: 2,
            human: String::new(),
        };
    }
    match arguments.command {
        Command::BootstrapFirstAdministrator(arguments) => crate::auth::bootstrap_command(
            &crate::auth::InputArguments {
                host_context: arguments.host_context,
                request: arguments.request,
                exec_spec: arguments.exec_spec,
            },
            target,
            dry_run,
            crate::auth::maintenance_handoff::SystemBrowser::current_process,
            diagnostics,
        ),
    }
}
