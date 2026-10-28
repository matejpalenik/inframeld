use crate::{Error, Result};
use std::{
    io::Read,
    process::{Command, Output, Stdio},
    thread,
    time::{Duration, Instant},
};

pub(crate) fn capture(command: &mut Command, timeout: Duration) -> Result<Output> {
    let stdout = tempfile::NamedTempFile::new()?;
    let stderr = tempfile::NamedTempFile::new()?;
    let mut child = command
        .stdout(Stdio::from(stdout.reopen()?))
        .stderr(Stdio::from(stderr.reopen()?))
        .spawn()
        .map_err(|error| Error::Invalid(format!("cannot start {command:?}: {error}")))?;
    let started = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() >= timeout {
            child.kill()?;
            child.wait()?;
            return Err(Error::Invalid(format!("command timed out: {command:?}")));
        }
        thread::sleep(Duration::from_millis(20));
    };
    let mut out = Vec::new();
    let mut err = Vec::new();
    stdout
        .reopen()?
        .take(4 * 1024 * 1024 + 1)
        .read_to_end(&mut out)?;
    stderr
        .reopen()?
        .take(4 * 1024 * 1024 + 1)
        .read_to_end(&mut err)?;
    if out.len() > 4 * 1024 * 1024 || err.len() > 4 * 1024 * 1024 {
        return Err(Error::Invalid("command output exceeds 4 MiB".into()));
    }
    Ok(Output {
        status,
        stdout: out,
        stderr: err,
    })
}

pub(crate) fn checked(command: &mut Command) -> Result<Output> {
    let result = capture(command, Duration::from_mins(10))?;
    if !result.status.success() {
        return Err(Error::Invalid(format!(
            "{command:?} failed: {}",
            String::from_utf8_lossy(&result.stderr)
        )));
    }
    Ok(result)
}
