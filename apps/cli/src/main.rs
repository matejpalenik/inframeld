//! Preserve plain-output pipe behavior after machine reporting owns its failures.

use std::io;
use std::process::ExitCode;

use inframeld_cli::run;

fn main() -> ExitCode {
    match run(
        std::env::args_os(),
        &mut io::stdout().lock(),
        &mut io::stderr().lock(),
    ) {
        Ok(code) => ExitCode::from(code),
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => ExitCode::SUCCESS,
        Err(_) => ExitCode::FAILURE,
    }
}
