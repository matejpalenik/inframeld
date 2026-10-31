//! Declare root selection and the implemented zero-argument version command.

use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
// Clap records independent switches. Dispatch resolves output and mode into enums.
#[allow(clippy::struct_excessive_bools)]
#[command(
    name = "inframeld",
    version,
    color = clap::ColorChoice::Never,
    about = "Work with Inframeld through its generated application client",
    after_help = "Examples:\n  inframeld --help\n  inframeld version\n  inframeld version --help\n\nInstalling this executable does not start or change an installation.\nProduct commands are delivered separately."
)]
pub(crate) struct Arguments {
    /// Emit one final versioned JSON result.
    #[arg(long, global = true)]
    pub json: bool,
    /// Emit an explicit final JSONL result record.
    #[arg(long, global = true)]
    pub jsonl: bool,
    /// Explain this invocation without performing its operation.
    #[arg(long, global = true)]
    pub dry_run: bool,
    /// Disable prompts and interactive input.
    #[arg(long, global = true)]
    pub no_input: bool,
    /// Keep human records unstyled and unwrapped.
    #[arg(long, global = true)]
    pub plain: bool,
    /// Disable output styling.
    #[arg(long, global = true)]
    pub no_color: bool,
    #[command(subcommand)]
    pub command: Option<Command>,
}

#[derive(Debug, Subcommand)]
pub(crate) enum Command {
    /// Show offline build information and qualified runtime pairing
    #[command(
        after_help = "Example: inframeld version\n\nThis reads embedded metadata only. Remote compatibility remains unverified."
    )]
    Version,
}
