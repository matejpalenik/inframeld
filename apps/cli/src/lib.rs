//! Command presentation and generated-client integration for Inframeld.

mod arguments;
pub mod client;
pub mod context;
pub mod metadata;
mod output;

use std::{
    ffi::OsString,
    io::{self, Write},
};

use arguments::{Arguments, Command};
use clap::{CommandFactory, Parser};

/// Run an invocation without loading persistent context or starting services.
///
/// # Errors
/// Returns an error if the selected output stream cannot be written.
pub fn run(
    arguments: impl IntoIterator<Item = impl Into<OsString> + Clone>,
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    let parsed = match Arguments::try_parse_from(arguments) {
        Ok(parsed) => parsed,
        Err(error) => {
            let code = u8::try_from(error.exit_code()).unwrap_or(1);
            if error.use_stderr() {
                write!(stderr, "{error}")?;
            } else {
                write!(stdout, "{error}")?;
            }
            return Ok(code);
        }
    };
    match parsed.command {
        Some(Command::Version) => output::version(stdout)?,
        None => {
            Arguments::command().write_long_help(stdout)?;
            writeln!(stdout)?;
        }
    }
    Ok(0)
}
