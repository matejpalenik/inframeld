//! Parse and dispatch one invocation without loading saved context or services.

use std::{
    ffi::OsString,
    io::{self, Write},
};

use clap::{CommandFactory, Parser};

use crate::{
    arguments::{Arguments, Command},
    commands,
};

/// Run an invocation without loading persistent context or starting services.
///
/// Help and argument errors use clap's selected stream and exit status. Version
/// reads embedded metadata only. Neither path writes configuration or uses a network.
///
/// # Errors
/// Returns an error if the selected output stream cannot be written, or embedded
/// build metadata is invalid. The executable owns final process-exit conversion.
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
        Some(Command::Version) => commands::version::run(stdout)?,
        None => {
            Arguments::command().write_long_help(stdout)?;
            writeln!(stdout)?;
        }
    }
    Ok(0)
}
