//! Describe the existing private packaging commands and their arguments.

use std::path::PathBuf;

use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(about = "Rust tooling for CLI packaging and native qualification")]
pub(crate) struct Arguments {
    #[command(subcommand)]
    pub(crate) command: Task,
}

#[derive(Debug, Subcommand)]
pub(crate) enum Task {
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
