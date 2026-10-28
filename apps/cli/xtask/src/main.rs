use clap::{Parser, Subcommand};
use inframeld_cli_xtask::{Result, archive, package, verify};
use std::{path::PathBuf, process::ExitCode};

#[derive(Debug, Parser)]
#[command(about = "Rust tooling for CLI packaging and native qualification")]
struct Arguments {
    #[command(subcommand)]
    command: Task,
}

#[derive(Debug, Subcommand)]
enum Task {
    /// Build, normalize and qualify a native archive without publishing
    Package {
        #[arg(long)]
        target: Option<String>,
        /// Force a second compilation and compare full artifact hashes
        #[arg(long)]
        reproducible: bool,
    },
    /// Normalize an existing local artifact
    Normalize {
        archive: PathBuf,
        #[arg(long)]
        epoch: u64,
    },
    /// Qualify a native artifact before claiming packaging success
    Verify {
        archive: PathBuf,
        #[arg(long)]
        target: String,
    },
}

fn run(arguments: Arguments) -> Result<()> {
    match arguments.command {
        Task::Package {
            target,
            reproducible,
        } => package::run(target, reproducible),
        Task::Normalize {
            archive: path,
            epoch,
        } => archive::normalize(&path, epoch),
        Task::Verify { archive, target } => {
            println!(
                "{}",
                serde_json::to_string_pretty(&verify::artifact(&archive, &target)?)?
            );
            Ok(())
        }
    }
}

fn main() -> ExitCode {
    match run(Arguments::parse()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}
