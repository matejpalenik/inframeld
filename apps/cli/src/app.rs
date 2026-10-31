//! Own offline argument intent, bounded final reporting and process-outcome meaning.

use std::{
    ffi::{OsStr, OsString},
    io::{self, Write},
};

use clap::{CommandFactory, Parser, error::ErrorKind};
use serde::Serialize;

use crate::{
    arguments::{Arguments, Command},
    commands::version::{self, VersionError},
};

const STDOUT_LIMIT: usize = 16_384;

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
}

#[derive(Debug, Clone, Copy)]
struct Intent {
    format: Format,
    mode: Mode,
    help: bool,
    conflict: bool,
}

impl Intent {
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
        ErrorBody {
            source: "cli",
            code: self.code(),
            message: self.message(),
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
struct ErrorBody {
    source: &'static str,
    code: &'static str,
    message: &'static str,
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
    warnings: [(); 0],
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct FinalRecord<'a, T> {
    schema_version: u8,
    #[serde(rename = "type")]
    kind: &'static str,
    result: &'a Envelope<T>,
}

/// Run an invocation without loading persistent context or starting services.
///
/// Static help and recognized clap version retain their plain-text channels.
/// Machine results and controlled parsing failures are bounded and never echo
/// submitted values. Dry-run explains the version read without performing it.
/// No path loads credentials, writes user state or contacts an installation.
///
/// # Errors
/// Returns plain-channel I/O failures for the executable's existing pipe policy.
/// Machine write or flush failure returns code 1 without a replacement result.
pub fn run(
    arguments: impl IntoIterator<Item = impl Into<OsString> + Clone>,
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    let mut arguments: Vec<OsString> = arguments.into_iter().map(Into::into).collect();
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
    match parsed.command {
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

fn report_help(
    arguments: &[OsString],
    stdout: &mut impl Write,
    stderr: &mut impl Write,
) -> io::Result<u8> {
    let first = arguments
        .iter()
        .skip(1)
        .take_while(|value| *value != "--")
        .find(|value| {
            !matches!(
                value.to_str(),
                Some(
                    "--json"
                        | "--jsonl"
                        | "--dry-run"
                        | "--no-input"
                        | "--plain"
                        | "--no-color"
                        | "-h"
                        | "--help"
                )
            )
        });
    let mut command = Arguments::command();
    // Prepare inherited global options and parent usage before selecting a child.
    command.build();
    let mut output = Vec::new();
    if first.is_some_and(|value| value == OsStr::new("version")) {
        let version = command
            .find_subcommand_mut("version")
            .ok_or_else(|| io::Error::other("Version help is unavailable."))?;
        version.write_long_help(&mut output)?;
    } else {
        command.write_long_help(&mut output)?;
    }
    output.push(b'\n');
    plain(&output, stdout, stderr)
}

fn plain(bytes: &[u8], stdout: &mut impl Write, stderr: &mut impl Write) -> io::Result<u8> {
    if bytes.len() > STDOUT_LIMIT {
        diagnostic(LocalError::OutputLimitExceeded, stderr)?;
        return Ok(1);
    }
    stdout.write_all(bytes)?;
    stdout.flush()?;
    Ok(0)
}

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
        warnings: [],
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
        diagnostic(error, stderr)?;
        return Ok(error.exit());
    }
    let _ = diagnostic(error, stderr);
    let result = Envelope::<()> {
        schema_version: 1,
        mode: intent.mode,
        outcome: Outcome::Failed,
        data: None,
        error: Some(error.body()),
        warnings: [],
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
