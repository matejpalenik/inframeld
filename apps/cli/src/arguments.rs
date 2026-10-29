//! Declare root selection and the implemented zero-argument version command.

use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(
    name = "inframeld",
    version,
    about = "Work with Inframeld through its generated application client",
    after_help = "Examples:\n  inframeld --help\n  inframeld version\n  inframeld version --help\n\nInstalling this executable does not start or change an installation.\nProduct commands are delivered separately."
)]
pub(crate) struct Arguments {
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
