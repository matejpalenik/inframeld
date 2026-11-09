//! Own offline argument intent, bounded final reporting and process-outcome meaning.

use std::{
    ffi::{OsStr, OsString},
    io::{self, IsTerminal as _, Write},
};

use clap::{CommandFactory, Parser, error::ErrorKind};
use serde::Serialize;

use crate::{
    arguments::{Arguments, Command},
    commands::{
        targets as target_commands,
        version::{self, VersionError},
    },
};

const STDOUT_LIMIT: usize = 128 * 1024;

/// Output intent is diagnostic-only until clap has accepted the invocation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Format {
    Human,
    Json,
    Jsonl,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
enum Mode {
    Execute,
    DryRun,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "camelCase")]
enum Outcome {
    Succeeded,
    Failed,
    Uncertain,
    Interrupted,
}

#[derive(Debug, Clone, Copy)]
struct Intent {
    format: Format,
    mode: Mode,
    help: bool,
    conflict: bool,
}

impl Intent {
    /// Recover safe output intent even when clap later rejects the invocation.
    fn inspect(arguments: &[OsString]) -> Self {
        let before_delimiter = arguments.iter().skip(1).take_while(|value| *value != "--");
        let mut json = false;
        let mut jsonl = false;
        let mut help = false;
        let mut mode = Mode::Execute;
        for value in before_delimiter {
            match value.to_str() {
                Some("-h" | "--help") => help = true,
                Some("--json") => json = true,
                Some("--jsonl") => jsonl = true,
                Some("--dry-run") => mode = Mode::DryRun,
                _ => {}
            }
        }
        Self {
            format: if json {
                Format::Json
            } else if jsonl {
                Format::Jsonl
            } else {
                Format::Human
            },
            mode,
            help,
            conflict: json && jsonl,
        }
    }
}

/// Fixed local failures cannot expose submitted arguments or arbitrary causes.
#[derive(Debug, Clone, Copy)]
enum LocalError {
    InvalidArguments,
    InvalidBuildMetadata,
    OutputLimitExceeded,
    OutputWriteFailed,
}

impl LocalError {
    fn code(self) -> &'static str {
        match self {
            Self::InvalidArguments => "invalid_arguments",
            Self::InvalidBuildMetadata => "invalid_build_metadata",
            Self::OutputLimitExceeded => "output_limit_exceeded",
            Self::OutputWriteFailed => "output_write_failed",
        }
    }

    fn message(self) -> &'static str {
        match self {
            Self::InvalidArguments => "Check the supplied arguments and use --help for usage.",
            Self::InvalidBuildMetadata => "Embedded build information is invalid.",
            Self::OutputLimitExceeded => "CLI output exceeds the supported size limit.",
            Self::OutputWriteFailed => "CLI output could not be written.",
        }
    }

    fn exit(self) -> u8 {
        if matches!(self, Self::InvalidArguments) {
            2
        } else {
            1
        }
    }

    fn body(self) -> ErrorBody {
        ErrorBody::Cli {
            code: self.code(),
            message: self.message().to_owned(),
        }
    }
}

impl From<VersionError> for LocalError {
    fn from(error: VersionError) -> Self {
        match error {
            VersionError::InvalidMetadata => Self::InvalidBuildMetadata,
            VersionError::OutputLimit => Self::OutputLimitExceeded,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(tag = "source", rename_all = "lowercase")]
enum ErrorBody {
    Cli {
        code: &'static str,
        message: String,
    },
    Backend {
        problem: crate::discovery::DiscoveryProblem,
    },
}

/// One typed final result is shared by version data and its explanation.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Envelope<T> {
    schema_version: u8,
    mode: Mode,
    outcome: Outcome,
    data: Option<T>,
    error: Option<ErrorBody>,
    warnings: Vec<target_commands::Warning>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct FinalRecord<'a, T> {
    schema_version: u8,
    #[serde(rename = "type")]
    kind: &'static str,
    result: &'a Envelope<T>,
}

/// Run the selected command with bounded reporting and explicit command effects.
///
/// Static help and recognized clap version retain their plain-text channels.
/// Machine results and controlled parsing failures are bounded and never echo
/// submitted values. Help and version are offline. Target commands can read or
/// update public local bindings and contact credential-free installation discovery.
/// Dry-run describes the selected operation without its network or write effects.
/// Explicit host-context bootstrap acquires transient proof for the reviewed host command.
/// No invocation selects a saved login or starts installation services.
/// The caller supplies terminal capability for this same output destination.
///
/// # Errors
/// Returns plain-channel I/O failures for the executable's existing pipe policy.
/// Machine write or flush failure returns code 1 without a replacement result.
pub fn run(
    arguments: impl IntoIterator<Item = impl Into<OsString> + Clone>,
    stdout: &mut impl Write,
    stderr: &mut impl Write,
    stdout_is_terminal: bool,
) -> io::Result<u8> {
    let mut arguments: Vec<OsString> = arguments.into_iter().map(Into::into).collect();
    if arguments.len() == 2
        && arguments[1] == crate::auth::maintenance_handoff::PRIVATE_BROWSER_LAUNCH_ARGUMENT
    {
        return Ok(u8::from(
            crate::auth::maintenance_handoff::run_system_browser_child().is_err(),
        ));
    }
    // The process label is not a command operand or safe diagnostic content.
    if let Some(label) = arguments.first_mut() {
        *label = "inframeld".into();
    } else {
        arguments.push("inframeld".into());
    }
    let intent = Intent::inspect(&arguments);
    if intent.help {
        return report_help(&arguments, stdout, stderr);
    }
    if intent.conflict {
        return failure(intent, LocalError::InvalidArguments, stdout, stderr);
    }
    let parsed = match Arguments::try_parse_from(&arguments) {
        Ok(parsed) => parsed,
        Err(error)
            if matches!(
                error.kind(),
                ErrorKind::DisplayHelp | ErrorKind::DisplayVersion
            ) =>
        {
            return plain(error.to_string().as_bytes(), stdout, stderr);
        }
        Err(_) => return failure(intent, LocalError::InvalidArguments, stdout, stderr),
    };

    let selected = Intent {
        format: if parsed.json {
            Format::Json
        } else if parsed.jsonl {
            Format::Jsonl
        } else {
            Format::Human
        },
        mode: if parsed.dry_run {
            Mode::DryRun
        } else {
            Mode::Execute
        },
        help: false,
        conflict: false,
    };
    let no_color = std::env::var_os("NO_COLOR");
    let term = std::env::var_os("TERM");
    let styled = human_styling(
        &parsed,
        stdout_is_terminal,
        no_color.as_deref(),
        term.as_deref(),
    );
    match parsed.command {
        Some(Command::Auth(arguments)) => {
            let execution = crate::commands::auth::run(
                arguments,
                parsed.target.as_deref(),
                parsed.dry_run,
                !parsed.no_input && io::stdin().is_terminal(),
                stderr,
            );
            report_bootstrap(selected, &execution, stdout, stderr)
        }
        Some(Command::Target(arguments)) => {
            let execution =
                target_commands::run(arguments, parsed.target.as_deref(), parsed.dry_run, stderr);
            report_target(selected, &execution, styled, stdout, stderr)
        }
        Some(Command::Version) if parsed.dry_run => success(
            selected,
            version::plan(),
            version::HUMAN_PLAN.as_bytes(),
            stdout,
            stderr,
        ),
        Some(Command::Version) => match version::execute() {
            Ok(metadata) => match version::data(&metadata) {
                Ok(data) => success(selected, data, metadata.render().as_bytes(), stdout, stderr),
                Err(error) => failure(selected, error.into(), stdout, stderr),
            },
            Err(error) => failure(selected, error.into(), stdout, stderr),
        },
        None if parsed.json || parsed.jsonl || parsed.dry_run => {
            failure(selected, LocalError::InvalidArguments, stdout, stderr)
        }
        None => report_help(&arguments, stdout, stderr),
    }
}

fn human_styling(
    arguments: &Arguments,
    stdout_is_terminal: bool,
    no_color: Option<&OsStr>,
    term: Option<&OsStr>,
) -> bool {
    stdout_is_terminal
        && !arguments.json
        && !arguments.jsonl
        && !arguments.plain
        && !arguments.no_color
        && no_color.is_none_or(OsStr::is_empty)
        && term != Some(OsStr::new("dumb"))
}

fn report_help(
    arguments: &[OsString],
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    let mut command = Arguments::command();
    command.build();
    let mut skip_value = false;
    for value in arguments.iter().skip(1).take_while(|value| *value != "--") {
        if skip_value {
            skip_value = false;
            continue;
        }
        let Some(token) = value.to_str() else { break };
        if matches!(
            token,
            "--json"
                | "--jsonl"
                | "--dry-run"
                | "--no-input"
                | "--plain"
                | "--no-color"
                | "-h"
                | "--help"
        ) {
            continue;
        }
        let (name, attached) = token
            .split_once('=')
            .map_or((token, false), |(name, _)| (name, true));
        if name == "--target"
            || (command.get_name() == "add" && matches!(name, "--url" | "--ca-cert" | "--proxy"))
        {
            skip_value = !attached;
            continue;
        }
        if let Some(child) = command.find_subcommand(token).cloned() {
            command = child;
        } else {
            break;
        }
    }
    let mut output = Vec::new();
    command.write_long_help(&mut output)?;
    output.push(b'\n');
    plain(&output, stdout, stderr)
}

fn report_bootstrap(
    intent: Intent,
    execution: &crate::auth::BootstrapExecution,
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    if let Some(error) = execution.error {
        let _ = writeln!(stderr, "error: {}", error.message());
    }
    if intent.format == Format::Human {
        if !execution.human.is_empty() && plain(execution.human.as_bytes(), stdout, stderr)? != 0 {
            return Ok(1);
        }
        return Ok(execution.exit);
    }
    let outcome = if matches!(execution.exit, 130 | 143) {
        Outcome::Interrupted
    } else if matches!(
        execution.error,
        Some(crate::auth::BootstrapError::Unconfirmed)
    ) {
        Outcome::Uncertain
    } else if execution.exit == 0 {
        Outcome::Succeeded
    } else {
        Outcome::Failed
    };
    let result = Envelope {
        schema_version: 1,
        mode: intent.mode,
        outcome,
        data: execution.data.as_ref(),
        error: execution.error.map(|error| ErrorBody::Cli {
            code: error.code(),
            message: error.message().to_owned(),
        }),
        warnings: vec![],
    };
    machine(intent, &result, execution.exit, stdout, stderr)
}

pub(crate) fn report_native_bootstrap(
    execution: &crate::auth::BootstrapExecution,
) -> std::process::ExitCode {
    let result = report_bootstrap(
        Intent {
            format: Format::Json,
            mode: Mode::Execute,
            help: false,
            conflict: false,
        },
        execution,
        &mut io::stdout().lock(),
        &mut io::stderr().lock(),
    );
    std::process::ExitCode::from(result.unwrap_or(1))
}

fn report_target(
    intent: Intent,
    execution: &target_commands::Execution,
    styled: bool,
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    let report = &execution.report;
    let human = report.human(styled);
    for warning in &report.warnings {
        let _ = writeln!(stderr, "warning: {}", warning.message);
    }
    if let Some(error) = &report.error {
        let _ = writeln!(stderr, "error: {error}");
    }
    if intent.format == Format::Human {
        if !human.is_empty() && plain(human.as_bytes(), stdout, stderr)? != 0 {
            return Ok(1);
        }
        return Ok(report.exit);
    }
    let outcome = match &report.error {
        None => Outcome::Succeeded,
        Some(crate::targets::TargetError::Uncertain) => Outcome::Uncertain,
        Some(crate::targets::TargetError::Interrupted) => Outcome::Interrupted,
        Some(_) => Outcome::Failed,
    };
    let result = Envelope {
        schema_version: 1,
        mode: intent.mode,
        outcome,
        data: report.data.as_ref(),
        error: report
            .error
            .as_ref()
            .map(|error| match error.backend_problem() {
                Some(problem) => ErrorBody::Backend {
                    problem: problem.clone(),
                },
                None => ErrorBody::Cli {
                    code: error.code(),
                    message: error.to_string(),
                },
            }),
        warnings: report.warnings.clone(),
    };
    machine(intent, &result, report.exit, stdout, stderr)
}

fn plain(bytes: &[u8], stdout: &mut impl Write, stderr: &mut impl Write) -> io::Result<u8> {
    if bytes.len() > STDOUT_LIMIT {
        let _ = diagnostic(LocalError::OutputLimitExceeded, stderr);
        return Ok(1);
    }
    stdout.write_all(bytes)?;
    stdout.flush()?;
    Ok(0)
}

/// Emit a fixed local diagnostic without echoing submitted arguments or causes.
fn diagnostic(error: LocalError, stderr: &mut impl Write) -> io::Result<()> {
    // At most two fixed reviewed lines can be attempted, together below 1 KiB.
    writeln!(stderr, "error: {}", error.message())?;
    stderr.flush()
}

fn success<T: Serialize>(
    intent: Intent,
    data: T,
    human: &[u8],
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    if intent.format == Format::Human {
        return plain(human, stdout, stderr);
    }
    let result = Envelope {
        schema_version: 1,
        mode: intent.mode,
        outcome: Outcome::Succeeded,
        data: Some(data),
        error: None,
        warnings: vec![],
    };
    machine(intent, &result, 0, stdout, stderr)
}

fn failure(
    intent: Intent,
    error: LocalError,
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    if intent.format == Format::Human {
        let _ = diagnostic(error, stderr);
        return Ok(error.exit());
    }
    let _ = diagnostic(error, stderr);
    let result = Envelope::<()> {
        schema_version: 1,
        mode: intent.mode,
        outcome: Outcome::Failed,
        data: None,
        error: Some(error.body()),
        warnings: vec![],
    };
    machine(intent, &result, error.exit(), stdout, stderr)
}

fn machine<T: Serialize>(
    intent: Intent,
    result: &Envelope<T>,
    exit: u8,
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    let encoded = match intent.format {
        Format::Jsonl => serde_json::to_vec(&FinalRecord {
            schema_version: 1,
            kind: "result",
            result,
        }),
        Format::Json | Format::Human => serde_json::to_vec_pretty(result),
    };
    // These closed typed records contain only serializable scalars and arrays.
    let mut bytes = encoded.map_err(|_| io::Error::other("CLI output could not be encoded."))?;
    bytes.push(b'\n');
    if bytes.len() > STDOUT_LIMIT {
        return failure(intent, LocalError::OutputLimitExceeded, stdout, stderr);
    }
    if stdout
        .write_all(&bytes)
        .and_then(|()| stdout.flush())
        .is_err()
    {
        let _ = diagnostic(LocalError::OutputWriteFailed, stderr);
        return Ok(1);
    }
    Ok(exit)
}

#[cfg(test)]
mod tests {
    use std::{
        ffi::OsStr,
        io::{self, Write},
    };

    use clap::Parser as _;

    use super::{Arguments, STDOUT_LIMIT, human_styling, plain};

    #[test]
    #[allow(clippy::expect_used)]
    fn styling_requires_the_supplied_terminal_and_respects_every_plain_veto() {
        for (flags, terminal, no_color, term, expected) in [
            (&[][..], true, None, Some("xterm-256color"), true),
            (&[][..], true, None, None, true),
            (&[][..], true, Some(""), Some("xterm"), true),
            (&["--dry-run"][..], true, None, Some("xterm"), true),
            (&["--no-input"][..], true, None, Some("xterm"), true),
            (&[][..], false, None, Some("xterm"), false),
            (&[][..], true, Some("1"), Some("xterm"), false),
            (&[][..], true, Some(" "), Some("xterm"), false),
            (&[][..], true, None, Some("dumb"), false),
            (&["--plain"][..], true, None, Some("xterm"), false),
            (&["--no-color"][..], true, None, Some("xterm"), false),
            (&["--json"][..], true, None, Some("xterm"), false),
            (&["--jsonl"][..], true, None, Some("xterm"), false),
        ] {
            let arguments = Arguments::try_parse_from(
                ["inframeld"]
                    .into_iter()
                    .chain(flags.iter().copied())
                    .chain(["target", "use", "dev"]),
            )
            .expect("The test supplies a valid target invocation.");
            assert_eq!(
                human_styling(
                    &arguments,
                    terminal,
                    no_color.map(OsStr::new),
                    term.map(OsStr::new)
                ),
                expected,
                "flags={flags:?}, terminal={terminal}, no_color={no_color:?}, term={term:?}",
            );
        }
    }

    #[derive(Debug)]
    enum DiagnosticFailure {
        Write,
        Flush,
    }

    impl Write for DiagnosticFailure {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            match self {
                Self::Write => Err(io::ErrorKind::BrokenPipe.into()),
                Self::Flush => Ok(bytes.len()),
            }
        }

        fn flush(&mut self) -> io::Result<()> {
            Err(io::ErrorKind::BrokenPipe.into())
        }
    }

    #[test]
    fn diagnostic_failure_keeps_the_plain_output_limit_rejection() {
        let codes = [DiagnosticFailure::Write, DiagnosticFailure::Flush].map(|mut diagnostic| {
            let mut output = Vec::new();
            let code = plain(&vec![b'x'; STDOUT_LIMIT + 1], &mut output, &mut diagnostic)
                .map_err(|error| error.kind());
            assert!(output.is_empty());
            code
        });
        assert_eq!(codes, [Ok(1), Ok(1)]);
    }
}
