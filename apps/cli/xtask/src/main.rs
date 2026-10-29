//! Enter private tooling and preserve its existing process-exit behavior.

mod app;
mod arguments;

use std::process::ExitCode;

use arguments::Arguments;
use clap::Parser;

fn main() -> ExitCode {
    match app::run(Arguments::parse()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}
