//! Preserve plain-output pipe behavior after machine reporting owns its failures.

use std::io::{self, IsTerminal as _};
use std::process::ExitCode;

use inframeld_cli::run;

fn main() -> ExitCode {
    let stdout = io::stdout();
    match run(
        std::env::args_os(),
        &mut stdout.lock(),
        &mut io::stderr().lock(),
        stdout.is_terminal(),
    ) {
        Ok(code) => ExitCode::from(code),
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => ExitCode::SUCCESS,
        Err(_) => ExitCode::FAILURE,
    }
}
