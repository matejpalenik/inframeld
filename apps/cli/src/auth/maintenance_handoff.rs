//! Own protected maintenance stdin, finite process execution and original receipts.

use std::{collections::BTreeMap, future::Future, path::PathBuf, process::Stdio, time::Duration};

use nix::{
    errno::Errno,
    sys::signal::{Signal, kill, killpg},
    unistd::Pid,
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    process::{Child, ChildStderr, ChildStdin, ChildStdout, Command},
};
use zeroize::Zeroizing;

use serde::{Deserialize, Serialize};
use tokio::time::Instant;

use super::recipient_proof::{
    InvalidReceipt, MaintenanceErrorCode, RecipientProof, RepairReceipt, RepairRequest,
};

/// A trusted host's direct argv descriptor, separate from the recipient's proof.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionSpec {
    program: PathBuf,
    args: Vec<String>,
    #[serde(default, deserialize_with = "deserialize_environment")]
    environment: BTreeMap<String, String>,
}

/// Invalid host descriptors never reach process creation or arbitrary diagnostics.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
#[error("The trusted maintenance execution descriptor is invalid.")]
pub struct InvalidExecutionSpec;

impl ExecutionSpec {
    /// Read one strict bounded direct-execution descriptor without ambient fallback.
    ///
    /// # Errors
    /// Rejects invalid fields, duplicate environment names and non-absolute programs.
    pub fn parse(bytes: &[u8]) -> Result<Self, InvalidExecutionSpec> {
        if bytes.len() > 65_536 {
            return Err(InvalidExecutionSpec);
        }
        let execution: Self = serde_json::from_slice(bytes).map_err(|_| InvalidExecutionSpec)?;
        if !execution.program.is_absolute()
            || execution
                .program
                .as_os_str()
                .as_encoded_bytes()
                .contains(&0)
            || execution.program.as_os_str().len() > 8192
            || execution.args.len() > 256
            || execution
                .args
                .iter()
                .any(|argument| argument.contains('\0') || argument.len() > 8192)
            || execution.environment.len() > 64
            || execution.environment.iter().any(|(name, value)| {
                name.is_empty() || name.contains(['=', '\0']) || value.contains('\0')
            })
        {
            return Err(InvalidExecutionSpec);
        }
        Ok(execution)
    }
}

/// Reject duplicate names at the intentionally dynamic host-environment boundary.
fn deserialize_environment<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<BTreeMap<String, String>, D::Error> {
    struct EnvironmentVisitor;
    impl<'de> serde::de::Visitor<'de> for EnvironmentVisitor {
        type Value = BTreeMap<String, String>;
        fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            formatter.write_str("unique explicit environment names and string values")
        }
        fn visit_map<A: serde::de::MapAccess<'de>>(
            self,
            mut access: A,
        ) -> Result<Self::Value, A::Error> {
            let mut environment = BTreeMap::new();
            while let Some((name, value)) = access.next_entry::<String, String>()? {
                if environment.insert(name, value).is_some() {
                    return Err(serde::de::Error::custom("duplicate environment name"));
                }
            }
            Ok(environment)
        }
    }
    deserializer.deserialize_map(EnvironmentVisitor)
}

impl std::fmt::Debug for ExecutionSpec {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("ExecutionSpec([host-controlled argv])")
    }
}

/// A local process outcome cannot substitute for an original after-commit receipt.
#[derive(Debug, Serialize)]
#[serde(tag = "status", rename_all = "kebab-case")]
pub enum MaintenanceEffect {
    /// No protected maintenance process was started.
    NotStarted,
    /// The exact request and verified principal match an after-commit receipt.
    Committed {
        /// Original bound receipt, independent of subsequent local cleanup.
        receipt: Box<RepairReceipt>,
    },
    /// The transport ended without proving whether the backend committed.
    Unknown {
        /// Keep this original ID for explicit inspection, never automatic resubmission.
        operation_id: String,
    },
}

/// Cleanup is an independent observation, never proof of backend rollback.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum CleanupStatus {
    /// No cleanup obligation was created, or an intentional handoff ended it.
    NotNeeded,
    /// The owned cleanup completed and was observed.
    Confirmed,
    /// Cleanup could not be confirmed within its finite budget.
    Unconfirmed,
}

/// Safe failure categories omit argv, raw output, provider errors and tokens.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum HandoffFailure {
    /// Input, proof or execution intent did not match before launch.
    InvalidBinding,
    /// The host transport could not start.
    Launch,
    /// The caller cancelled the owned process.
    Cancelled,
    /// The original or ordinary process budget expired.
    TimedOut,
    /// Protected stdin could not be delivered within its budget.
    Input,
    /// Output was unavailable or exceeded its bound.
    Output,
    /// The child exited unsuccessfully.
    Exit,
}

/// Keep committed facts, process failure and cleanup uncertainty separate.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HandoffOutcome {
    /// Receipt evidence or original-operation uncertainty.
    pub effect: MaintenanceEffect,
    /// Observed termination, group retirement, reaping and stream completion.
    pub process_cleanup: CleanupStatus,
    /// A transport failure may accompany an already proven commit.
    pub failure: Option<HandoffFailure>,
    /// Passive direct-child evidence does not replace an original receipt.
    #[serde(skip)]
    pub child_status: ChildStatus,
    /// A strictly bound backend code is diagnostic, not proof of rollback.
    #[serde(skip)]
    pub backend_error: Option<MaintenanceErrorCode>,
}

/// Preserve the retained wait observation without inventing a status for missing evidence.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChildStatus {
    /// No authoritative child status was observed.
    Unobserved,
    /// The direct child exited normally with this bounded status.
    Exited(u8),
    /// The direct child terminated under this observed signal.
    Signaled(u8),
}

impl std::fmt::Display for ChildStatus {
    fn fmt(&self, output: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Unobserved => output.write_str("unobserved"),
            Self::Exited(code) => write!(output, "exit-{code}"),
            Self::Signaled(signal) => write!(output, "signal-{signal}"),
        }
    }
}

/// Submit a verified recipient proof once through protected host stdin.
///
/// This repair-only operation never retries. Killing Docker/exec transport does
/// not prove backend termination or rollback. Callers must await cancellation
/// finalization instead of dropping the whole operation as a cleanup claim.
pub async fn handoff(
    execution: &ExecutionSpec,
    request: &RepairRequest,
    proof: &RecipientProof,
    deadline: Instant,
    cancellation: impl Future<Output = ()>,
) -> HandoffOutcome {
    handoff_with_budgets(
        execution,
        request,
        proof,
        deadline,
        cancellation,
        ProcessBudgets::maintenance(),
    )
    .await
}

#[derive(Clone, Copy)]
struct ProcessBudgets {
    execution: Duration,
    stdin: Duration,
    term: Duration,
    kill: Duration,
}
impl ProcessBudgets {
    fn maintenance() -> Self {
        Self {
            execution: Duration::from_secs(30),
            stdin: Duration::from_secs(5),
            term: Duration::from_secs(5),
            kill: Duration::from_secs(5),
        }
    }
}

/// Retain the immutable proof-free values while adding the opaque token only in memory.
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ProtectedRequest<'a> {
    #[serde(flatten)]
    request: &'a RepairRequest,
    identity_proof: IdentityProof<'a>,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct IdentityProof<'a> {
    kind: &'static str,
    access_token: &'a str,
}

async fn handoff_with_budgets(
    execution: &ExecutionSpec,
    request: &RepairRequest,
    proof: &RecipientProof,
    deadline: Instant,
    cancellation: impl Future<Output = ()>,
    budgets: ProcessBudgets,
) -> HandoffOutcome {
    let not_started = |failure| HandoffOutcome {
        effect: MaintenanceEffect::NotStarted,
        process_cleanup: CleanupStatus::NotNeeded,
        failure: Some(failure),
        child_status: ChildStatus::Unobserved,
        backend_error: None,
    };
    if proof.installation_id != request.expected_installation_id
        || proof.identity_id != request.expected_identity_id
    {
        return not_started(HandoffFailure::InvalidBinding);
    }
    let input = match serde_json::to_vec(&ProtectedRequest {
        request,
        identity_proof: IdentityProof {
            kind: "hydra-access-token",
            access_token: &proof.access_token,
        },
    }) {
        Ok(input) if input.len() <= 65_536 => Zeroizing::new(input),
        _ => return not_started(HandoffFailure::InvalidBinding),
    };
    if Instant::now() >= deadline {
        return not_started(HandoffFailure::TimedOut);
    }
    let mut cancellation = std::pin::pin!(cancellation);
    let cancelled = std::future::poll_fn(|context| {
        std::task::Poll::Ready(cancellation.as_mut().poll(context).is_ready())
    })
    .await;
    if cancelled {
        return not_started(HandoffFailure::Cancelled);
    }
    let Ok(mut process) = OwnedProcess::spawn(execution, ProcessPurpose::Maintenance) else {
        return not_started(HandoffFailure::Launch);
    };
    let operation_deadline = deadline.min(Instant::now() + budgets.execution);
    let mut failure = {
        let operation = process.run(&input, operation_deadline, budgets.stdin);
        tokio::pin!(operation);
        tokio::select! {
            biased;
            () = cancellation.as_mut() => Some(HandoffFailure::Cancelled),
            () = tokio::time::sleep_until(operation_deadline) => Some(HandoffFailure::TimedOut),
            result = &mut operation => result.err(),
        }
    };
    let confirmed = process.finalize(budgets.term, budgets.kill).await;
    let (receipt, backend_error) =
        if process.stdout.complete && !process.stdout.overflow && !process.stdout.failed {
            match request.validate_receipt(&process.stdout.bytes, proof.principal_id) {
                Ok(receipt) => (Some(receipt), None),
                Err(InvalidReceipt::Backend { code }) => (None, Some(code)),
                Err(InvalidReceipt::Unavailable) => (None, None),
            }
        } else {
            (None, None)
        };
    let effect = if let Some(receipt) = receipt {
        MaintenanceEffect::Committed {
            receipt: Box::new(receipt),
        }
    } else {
        if failure.is_none() {
            failure = Some(HandoffFailure::Output);
        }
        MaintenanceEffect::Unknown {
            operation_id: request.operation_id.clone(),
        }
    };
    HandoffOutcome {
        effect,
        process_cleanup: if confirmed {
            CleanupStatus::Confirmed
        } else {
            CleanupStatus::Unconfirmed
        },
        failure,
        child_status: process.anchor.outcome,
        backend_error,
    }
}

/// Keep an unreaped leader as the anchor for every signal to its owned group.
struct ProcessAnchor {
    pid: Option<Pid>,
    observed: Option<bool>,
    outcome: ChildStatus,
    ownership: LeaderOwnership,
    group_owned: bool,
}
/// Only a retained unreaped leader permits further direct or group signals.
#[derive(Clone, Copy, PartialEq, Eq)]
enum LeaderOwnership {
    Retained,
    HandedOff,
    Reaped,
    Lost,
}
impl ProcessAnchor {
    fn observe(&mut self) -> Result<Option<bool>, HandoffFailure> {
        if let Some(success) = self.observed {
            return Ok(Some(success));
        }
        if self.ownership != LeaderOwnership::Retained {
            return Err(HandoffFailure::Exit);
        }
        let pid = rustix::process::Pid::from_raw(self.pid.ok_or(HandoffFailure::Exit)?.as_raw())
            .ok_or(HandoffFailure::Exit)?;
        let observation = rustix::process::waitid(
            rustix::process::WaitId::Pid(pid),
            rustix::process::WaitIdOptions::EXITED
                | rustix::process::WaitIdOptions::NOHANG
                | rustix::process::WaitIdOptions::NOWAIT,
        );
        self.record_observation(observation)
    }
    /// An interrupted readonly query does not discard the unreaped owner.
    fn record_observation(
        &mut self,
        observation: rustix::io::Result<Option<rustix::process::WaitIdStatus>>,
    ) -> Result<Option<bool>, HandoffFailure> {
        match observation {
            Ok(Some(status)) => {
                self.outcome = status
                    .exit_status()
                    .and_then(|value| u8::try_from(value).ok())
                    .map(ChildStatus::Exited)
                    .or_else(|| {
                        status
                            .terminating_signal()
                            .and_then(|value| u8::try_from(value).ok())
                            .map(ChildStatus::Signaled)
                    })
                    .unwrap_or(ChildStatus::Unobserved);
                let success = status.exited() && status.exit_status() == Some(0);
                self.observed = Some(success);
                Ok(Some(success))
            }
            Ok(None) | Err(rustix::io::Errno::INTR) => Ok(None),
            Err(error) => {
                if error == rustix::io::Errno::CHILD {
                    self.ownership = LeaderOwnership::Lost;
                }
                Err(HandoffFailure::Exit)
            }
        }
    }
    async fn wait_observed(&mut self) -> Result<(), HandoffFailure> {
        loop {
            match self.observe()? {
                Some(true) => return Ok(()),
                Some(false) => return Err(HandoffFailure::Exit),
                None => tokio::time::sleep(Duration::from_millis(10)).await,
            }
        }
    }
    fn signal(&self, signal: Signal) -> bool {
        self.ownership == LeaderOwnership::Retained
            && self.pid.is_some_and(|pid| {
                if self.group_owned {
                    killpg(pid, signal).is_ok()
                } else {
                    kill(pid, signal).is_ok()
                }
            })
    }
}

/// Bound retained bytes while continuing to discard overflow during finalization.
struct BoundedOutput<R> {
    reader: Option<R>,
    bytes: Zeroizing<Vec<u8>>,
    buffer: Zeroizing<Vec<u8>>,
    limit: usize,
    complete: bool,
    overflow: bool,
    failed: bool,
}
impl<R: AsyncRead + Unpin> BoundedOutput<R> {
    fn new(reader: Option<R>, limit: usize, required: bool) -> Self {
        let missing = reader.is_none();
        Self {
            reader,
            bytes: Zeroizing::new(Vec::new()),
            buffer: Zeroizing::new(vec![0_u8; 4096]),
            limit,
            complete: missing,
            overflow: false,
            failed: missing && required,
        }
    }
    async fn step(&mut self) -> Result<(), HandoffFailure> {
        if self.complete {
            return Ok(());
        }
        let Some(reader) = self.reader.as_mut() else {
            return Err(HandoffFailure::Output);
        };
        let count = match reader.read(&mut self.buffer[..]).await {
            Ok(count) => count,
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => return Ok(()),
            Err(_) => {
                self.failed = true;
                self.complete = true;
                return Err(HandoffFailure::Output);
            }
        };
        if count == 0 {
            self.complete = true;
            return Ok(());
        }
        let retained = (self.limit - self.bytes.len()).min(count);
        self.bytes.extend_from_slice(&self.buffer[..retained]);
        if retained < count {
            self.overflow = true;
            return Err(HandoffFailure::Output);
        }
        Ok(())
    }
    async fn collect(&mut self) -> Result<(), HandoffFailure> {
        while !self.complete {
            self.step().await?;
        }
        if self.failed {
            Err(HandoffFailure::Output)
        } else {
            Ok(())
        }
    }
    async fn drain(&mut self) {
        while !self.complete {
            let _ = self.step().await;
        }
    }
}

#[derive(Clone, Copy)]
enum ProcessPurpose {
    Maintenance,
    Browser,
}

/// Own the child and both drains. Drop is best effort, never a reaping receipt.
struct OwnedProcess {
    child: Child,
    anchor: ProcessAnchor,
    stdin: Option<ChildStdin>,
    stdout: BoundedOutput<ChildStdout>,
    stderr: BoundedOutput<ChildStderr>,
}
impl OwnedProcess {
    fn spawn(execution: &ExecutionSpec, purpose: ProcessPurpose) -> Result<Self, ()> {
        let mut command = Command::new(&execution.program);
        command
            .args(&execution.args)
            .env_clear()
            .envs(&execution.environment)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped());
        match purpose {
            ProcessPurpose::Maintenance => {
                command.stderr(Stdio::piped()).process_group(0);
            }
            ProcessPurpose::Browser => {
                command.stderr(Stdio::null());
            }
        }
        let mut child = command.spawn().map_err(|_| ())?;
        let pid = child
            .id()
            .and_then(|pid| i32::try_from(pid).ok())
            .filter(|pid| *pid > 0)
            .map(Pid::from_raw);
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        Ok(Self {
            child,
            anchor: ProcessAnchor {
                pid,
                observed: None,
                outcome: ChildStatus::Unobserved,
                ownership: if pid.is_some() {
                    LeaderOwnership::Retained
                } else {
                    LeaderOwnership::Lost
                },
                group_owned: matches!(purpose, ProcessPurpose::Maintenance),
            },
            stdin,
            stdout: BoundedOutput::new(
                stdout,
                if matches!(purpose, ProcessPurpose::Maintenance) {
                    65_536
                } else {
                    16
                },
                true,
            ),
            stderr: BoundedOutput::new(
                stderr,
                16 * 1024,
                matches!(purpose, ProcessPurpose::Maintenance),
            ),
        })
    }
    async fn run(
        &mut self,
        input: &[u8],
        deadline: Instant,
        stdin_budget: Duration,
    ) -> Result<(), HandoffFailure> {
        let stdin = self.stdin.take().ok_or(HandoffFailure::Input)?;
        let writing = write_child_input(stdin, input, deadline, stdin_budget);
        // No Tokio wait/try_wait is polled here. NOWAIT retains the leader until
        // all necessary group signals have been sent by the single finalizer.
        tokio::try_join!(
            writing,
            self.stdout.collect(),
            self.stderr.collect(),
            self.anchor.wait_observed()
        )?;
        Ok(())
    }
    fn admit_browser_session(&mut self) -> bool {
        let Some(pid) = self.anchor.pid else {
            return false;
        };
        if self.anchor.ownership != LeaderOwnership::Retained
            || nix::unistd::getpgid(Some(pid)) != Ok(pid)
            || nix::unistd::getsid(Some(pid)) != Ok(pid)
        {
            return false;
        }
        self.anchor.group_owned = true;
        true
    }
    async fn reap_browser_handoff(&mut self, deadline: Instant) -> bool {
        // The launcher already reported success without reaping. Its GUI group
        // is intentionally handed to the OS. No later failure may signal it.
        self.anchor.ownership = LeaderOwnership::HandedOff;
        match tokio::time::timeout_at(deadline, self.child.wait()).await {
            Ok(result) => {
                self.anchor.ownership = if result.is_ok() {
                    LeaderOwnership::Reaped
                } else {
                    LeaderOwnership::Lost
                };
                result.is_ok_and(|status| status.success())
            }
            Err(_) => false,
        }
    }
    async fn finalize(&mut self, term_budget: Duration, kill_budget: Duration) -> bool {
        drop(self.stdin.take());
        if self.anchor.ownership != LeaderOwnership::Retained {
            return false;
        }
        let _ = self.anchor.signal(Signal::SIGTERM);
        let term_deadline = Instant::now() + term_budget;
        loop {
            if self.anchor.observe().is_err() && self.anchor.ownership != LeaderOwnership::Retained
            {
                return false;
            }
            if self.anchor.observed.is_some() && self.stdout.complete && self.stderr.complete {
                break;
            }
            tokio::select! {
                ()=tokio::time::sleep_until(term_deadline)=>break,
                _=self.stdout.step(), if !self.stdout.complete=>{},
                _=self.stderr.step(), if !self.stderr.complete=>{},
                ()=tokio::time::sleep(Duration::from_millis(10))=>{},
            }
        }
        // A retained zombie can keep its group probe positive. Kill remaining
        // members while ownership is pinned, then reap once, without a signal
        // after reaping even if a later numerical group probe is positive.
        let _ = self.anchor.signal(Signal::SIGKILL);
        let kill_deadline = Instant::now() + kill_budget;
        let reaping = async {
            let result = self.child.wait().await;
            self.anchor.ownership = if result.is_ok() {
                LeaderOwnership::Reaped
            } else {
                LeaderOwnership::Lost
            };
            result.map_err(|_| ())
        };
        let finishing = async {
            let (reaped, (), ()) = tokio::join!(reaping, self.stdout.drain(), self.stderr.drain());
            reaped
        };
        if !matches!(
            tokio::time::timeout_at(kill_deadline, finishing).await,
            Ok(Ok(_))
        ) {
            return false;
        }
        if !self.anchor.group_owned {
            return !self.stdout.failed && !self.stderr.failed;
        }
        let Some(pid) = self.anchor.pid else {
            return false;
        };
        loop {
            match killpg(pid, None) {
                Err(Errno::ESRCH) => {
                    return !self.stdout.failed && !self.stderr.failed;
                }
                // A permission failure is not proof of absence. Darwin can
                // report it while the killed orphan group is retiring. Keep
                // observing within the same deadline without another signal.
                Err(Errno::EINTR | Errno::EPERM) | Ok(()) => {}
                Err(_) => return false,
            }
            if Instant::now() >= kill_deadline {
                return false;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }
}
impl Drop for OwnedProcess {
    fn drop(&mut self) {
        if self.anchor.ownership == LeaderOwnership::Retained && self.child.id().is_some() {
            let _ = self.anchor.signal(Signal::SIGKILL);
        }
    }
}

/// Own the writer through bounded input and EOF, including backpressure or cancellation.
async fn write_child_input(
    mut stdin: impl AsyncWrite + Unpin,
    input: &[u8],
    deadline: Instant,
    budget: Duration,
) -> Result<(), HandoffFailure> {
    tokio::time::timeout_at(deadline.min(Instant::now() + budget), async {
        stdin
            .write_all(input)
            .await
            .map_err(|_| HandoffFailure::Input)?;
        stdin.shutdown().await.map_err(|_| HandoffFailure::Input)
    })
    .await
    .map_err(|_| HandoffFailure::Input)?
}

/// Reserved dispatch argument for the maintained helper's fresh launcher child.
/// It never performs OAuth or emits credentials and is not a main CLI command.
pub const PRIVATE_BROWSER_LAUNCH_ARGUMENT: &str = "--internal-system-browser-launch";

/// Re-execute the maintained helper so a blocking desktop handler remains bounded.
pub struct SystemBrowser {
    execution: ExecutionSpec,
    used: bool,
}
impl SystemBrowser {
    /// Freeze the actual helper executable and explicit GUI/session environment.
    ///
    /// # Errors
    /// Rejects an unavailable executable or non-UTF-8 selected environment value.
    pub fn current_process() -> Result<Self, super::flow::BrowserLaunchError> {
        let program =
            std::env::current_exe().map_err(|_| super::flow::BrowserLaunchError::failed())?;
        let mut environment = BTreeMap::new();
        for name in [
            "PATH",
            "HOME",
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "XAUTHORITY",
            "XDG_CURRENT_DESKTOP",
            "DESKTOP_SESSION",
            "XDG_SESSION_TYPE",
            "XDG_CONFIG_HOME",
        ] {
            if let Some(value) = std::env::var_os(name) {
                environment.insert(
                    name.into(),
                    value
                        .into_string()
                        .map_err(|_| super::flow::BrowserLaunchError::failed())?,
                );
            }
        }
        Ok(Self {
            execution: ExecutionSpec {
                program,
                args: vec![PRIVATE_BROWSER_LAUNCH_ARGUMENT.into()],
                environment,
            },
            used: false,
        })
    }
}
impl std::fmt::Debug for SystemBrowser {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("SystemBrowser([owned private launcher])")
    }
}
impl super::flow::BrowserLauncher for SystemBrowser {
    async fn open(
        &mut self,
        ready: &super::flow::AuthorizationReady,
        deadline: Instant,
        mut cancellation: std::pin::Pin<&mut (dyn Future<Output = ()> + Send)>,
    ) -> Result<(), super::flow::BrowserLaunchError> {
        use super::flow::{BrowserFailureKind, BrowserLaunchError};
        if self.used {
            return Err(BrowserLaunchError::failed());
        }
        self.used = true;
        let cancelled = std::future::poll_fn(|context| {
            std::task::Poll::Ready(cancellation.as_mut().poll(context).is_ready())
        })
        .await;
        if cancelled {
            return Err(BrowserLaunchError {
                kind: BrowserFailureKind::Cancelled,
                resource_cleanup: CleanupStatus::NotNeeded,
            });
        }
        if Instant::now() >= deadline {
            return Err(BrowserLaunchError {
                kind: BrowserFailureKind::TimedOut,
                resource_cleanup: CleanupStatus::NotNeeded,
            });
        }
        let input = Zeroizing::new(
            serde_json::to_vec(&BrowserChildInput {
                schema_version: 1,
                authorization_url: ready.authorization_url.as_str().to_owned(),
            })
            .map_err(|_| BrowserLaunchError::failed())?,
        );
        if input.len() > 128 * 1024 {
            return Err(BrowserLaunchError::failed());
        }
        let launch_deadline = deadline.min(Instant::now() + Duration::from_secs(5));
        let mut process = OwnedProcess::spawn(&self.execution, ProcessPurpose::Browser)
            .map_err(|()| BrowserLaunchError::failed())?;
        let result=async {
            tokio::select! {
                biased;
                ()=cancellation.as_mut()=>return Err(BrowserFailureKind::Cancelled),
                ()=tokio::time::sleep_until(launch_deadline)=>return Err(BrowserFailureKind::TimedOut),
                result=process.stdout.collect()=>result.map_err(|_|BrowserFailureKind::Failed)?,
            }
            // EOF is mandatory. The child has safely replaced stdout with null,
            // before receiving the URL or admitting desktop-handler effects.
            if process.stdout.bytes.as_slice()!=b"READY1\n" || !process.admit_browser_session() {
                return Err(BrowserFailureKind::Failed);
            }
            tokio::select! {
                biased;
                ()=cancellation.as_mut()=>Err(BrowserFailureKind::Cancelled),
                ()=tokio::time::sleep_until(launch_deadline)=>Err(BrowserFailureKind::TimedOut),
                result=process.run(&input,launch_deadline,Duration::from_secs(5))=>result.map_err(|_|BrowserFailureKind::Failed),
            }
        }.await;
        if result.is_ok() {
            return if process.reap_browser_handoff(launch_deadline).await {
                Ok(())
            } else {
                Err(BrowserLaunchError {
                    kind: BrowserFailureKind::Failed,
                    resource_cleanup: CleanupStatus::Unconfirmed,
                })
            };
        }
        let confirmed = process
            .finalize(Duration::from_secs(5), Duration::from_secs(5))
            .await;
        Err(BrowserLaunchError {
            kind: result.err().unwrap_or(BrowserFailureKind::Failed),
            resource_cleanup: if confirmed {
                CleanupStatus::Confirmed
            } else {
                CleanupStatus::Unconfirmed
            },
        })
    }
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct BrowserChildInput {
    schema_version: u8,
    authorization_url: String,
}

/// Fixed private-mode failure codes never contain URL or OS diagnostic content.
#[derive(Debug, Clone, Copy, thiserror::Error)]
pub enum BrowserChildError {
    /// A fresh detached session could not be established.
    #[error("The private launcher could not detach.")]
    Detach,
    /// The exact parent acknowledgement could not complete.
    #[error("The private launcher handshake failed.")]
    Handshake,
    /// Protected input was invalid or unsupported.
    #[error("The private launcher input was invalid.")]
    Input,
    /// The maintained native browser library did not accept dispatch.
    #[error("The native browser dispatch failed.")]
    Launch,
}

/// Execute only the maintained example's earliest exact private child branch.
///
/// Creates a new session before reading navigation data, acknowledges once,
/// replaces stdout with null before URL admission, then invokes the maintained
/// hardened browser library with null standard streams and no logger.
///
/// # Errors
/// Returns fixed categories. The caller maps them to an exit without printing.
/// Never invoke this in the parent process or after initializing other workers.
pub fn run_system_browser_child() -> Result<(), BrowserChildError> {
    use std::io::{Read as _, Write as _};
    nix::unistd::setsid().map_err(|_| BrowserChildError::Detach)?;
    if std::env::var_os("BROWSER").is_some() || std::env::var_os("RUST_LOG").is_some() {
        return Err(BrowserChildError::Input);
    }
    let null = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/null")
        .map_err(|_| BrowserChildError::Handshake)?;
    {
        let mut acknowledgement = std::io::stdout().lock();
        acknowledgement
            .write_all(b"READY1\n")
            .map_err(|_| BrowserChildError::Handshake)?;
        acknowledgement
            .flush()
            .map_err(|_| BrowserChildError::Handshake)?;
    }
    nix::unistd::dup2_stdout(&null).map_err(|_| BrowserChildError::Handshake)?;
    nix::unistd::dup2_stderr(&null).map_err(|_| BrowserChildError::Handshake)?;
    let mut bytes = Zeroizing::new(Vec::new());
    std::io::stdin()
        .lock()
        .take(128 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| BrowserChildError::Input)?;
    if bytes.len() > 128 * 1024 {
        return Err(BrowserChildError::Input);
    }
    let input: BrowserChildInput =
        serde_json::from_slice(&bytes).map_err(|_| BrowserChildError::Input)?;
    let url = Zeroizing::new(input.authorization_url);
    let parsed = url::Url::parse(&url).map_err(|_| BrowserChildError::Input)?;
    if input.schema_version != 1
        || parsed.scheme() != "https"
        || parsed.host_str().is_none()
        || !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.fragment().is_some()
        || url
            .chars()
            .any(|character| character.is_control() || character.is_whitespace())
        || url.contains('\\')
    {
        return Err(BrowserChildError::Input);
    }
    nix::unistd::dup2_stdin(&null).map_err(|_| BrowserChildError::Input)?;
    let mut options = webbrowser::BrowserOptions::new();
    options.with_suppress_output(true);
    webbrowser::open_browser_with_options(webbrowser::Browser::Default, &url, &options)
        .map_err(|_| BrowserChildError::Launch)
}

/// Write one flow-sensitive browser event to a protected same-UID fixture socket.
///
/// The fixture owns its fresh 0700 parent. This is not authentication against a
/// compromised process belonging to the same UID, and it accepts no claims.
pub struct NativeBrowserBridge {
    path: PathBuf,
    used: bool,
}
impl std::fmt::Debug for NativeBrowserBridge {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("NativeBrowserBridge([protected fixture IPC])")
    }
}
impl NativeBrowserBridge {
    /// Capture a fixture-owned absent socket path without binding or replacing it.
    #[must_use]
    pub fn new(path: PathBuf) -> Self {
        Self { path, used: false }
    }
}
impl super::flow::BrowserLauncher for NativeBrowserBridge {
    async fn open(
        &mut self,
        ready: &super::flow::AuthorizationReady,
        deadline: Instant,
        mut cancellation: std::pin::Pin<&mut (dyn Future<Output = ()> + Send)>,
    ) -> Result<(), super::flow::BrowserLaunchError> {
        use super::flow::{BrowserFailureKind, BrowserLaunchError};
        if self.used {
            return Err(BrowserLaunchError::failed());
        }
        self.used = true;
        let cancelled = std::future::poll_fn(|context| {
            std::task::Poll::Ready(cancellation.as_mut().poll(context).is_ready())
        })
        .await;
        if cancelled {
            return Err(BrowserLaunchError {
                kind: BrowserFailureKind::Cancelled,
                resource_cleanup: CleanupStatus::NotNeeded,
            });
        }
        if Instant::now() >= deadline {
            return Err(BrowserLaunchError {
                kind: BrowserFailureKind::TimedOut,
                resource_cleanup: CleanupStatus::NotNeeded,
            });
        }
        let mut event = Zeroizing::new(
            serde_json::to_vec(&BrowserEvent {
                schema_version: 1,
                kind: "authorization-ready",
                authorization_url: ready.authorization_url.as_str(),
                issuer: &ready.issuer,
                callback_uri: &ready.callback_uri,
            })
            .map_err(|_| BrowserLaunchError::failed())?,
        );
        if event.len() >= 128 * 1024 {
            return Err(BrowserLaunchError::failed());
        }
        event.push(b'\n');
        let mut owner =
            OwnedBridgeSocket::bind(self.path.clone()).map_err(|cleanup| BrowserLaunchError {
                kind: BrowserFailureKind::Failed,
                resource_cleanup: cleanup,
            })?;
        let result=async {
            let listener=owner.listener.as_ref().ok_or(BrowserFailureKind::Failed)?;
            let accepting_deadline=deadline.min(Instant::now()+Duration::from_secs(5));
            let (stream,_)=tokio::select! {
                biased;
                ()=cancellation.as_mut()=>return Err(BrowserFailureKind::Cancelled),
                ()=tokio::time::sleep_until(accepting_deadline)=>return Err(BrowserFailureKind::TimedOut),
                connection=listener.accept()=>connection.map_err(|_|BrowserFailureKind::Failed)?,
            };
            if stream.peer_cred().map_err(|_|BrowserFailureKind::Failed)?.uid()!=nix::unistd::geteuid().as_raw() {
                return Err(BrowserFailureKind::Failed);
            }
            owner.stream=Some(stream);
            let stream=owner.stream.as_mut().ok_or(BrowserFailureKind::Failed)?;
            let writing=async {
                stream.write_all(&event).await.map_err(|_|BrowserFailureKind::Failed)?;
                stream.shutdown().await.map_err(|_|BrowserFailureKind::Failed)
            };
            let writing_deadline=deadline.min(Instant::now()+Duration::from_secs(5));
            tokio::select! {
                biased;
                ()=cancellation.as_mut()=>Err(BrowserFailureKind::Cancelled),
                ()=tokio::time::sleep_until(writing_deadline)=>Err(BrowserFailureKind::TimedOut),
                result=writing=>result,
            }
        }.await;
        // Both waits have ended. Close the single stream/listener and observe
        // exact-inode removal before returning cancellation or normal completion.
        let confirmed = owner.close();
        match result {
            Ok(()) if confirmed => Ok(()),
            result => Err(BrowserLaunchError {
                kind: result.err().unwrap_or(BrowserFailureKind::Failed),
                resource_cleanup: if confirmed {
                    CleanupStatus::Confirmed
                } else {
                    CleanupStatus::Unconfirmed
                },
            }),
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BrowserEvent<'a> {
    schema_version: u8,
    #[serde(rename = "type")]
    kind: &'static str,
    authorization_url: &'a str,
    issuer: &'a str,
    callback_uri: &'a str,
}

/// Own only this newly bound pathname and kernel sockets. The fixture retains
/// its parent directory and no pre-existing entry is ever replaced or removed.
struct OwnedBridgeSocket {
    path: PathBuf,
    device: u64,
    inode: u64,
    listener: Option<tokio::net::UnixListener>,
    stream: Option<tokio::net::UnixStream>,
    closed: bool,
    cleanup_confirmed: bool,
}
impl OwnedBridgeSocket {
    fn bind(path: PathBuf) -> Result<Self, CleanupStatus> {
        use std::os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt};
        let parent = path
            .parent()
            .filter(|_| path.is_absolute())
            .ok_or(CleanupStatus::NotNeeded)?;
        let metadata = std::fs::symlink_metadata(parent).map_err(|_| CleanupStatus::NotNeeded)?;
        if metadata.file_type().is_symlink()
            || !metadata.is_dir()
            || metadata.uid() != nix::unistd::geteuid().as_raw()
            || metadata.mode() & 0o7777 != 0o700
        {
            return Err(CleanupStatus::NotNeeded);
        }
        match std::fs::symlink_metadata(&path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            _ => return Err(CleanupStatus::NotNeeded),
        }
        let listener =
            tokio::net::UnixListener::bind(&path).map_err(|_| CleanupStatus::NotNeeded)?;
        let metadata = std::fs::symlink_metadata(&path).map_err(|_| CleanupStatus::Unconfirmed)?;
        if !metadata.file_type().is_socket() || metadata.uid() != nix::unistd::geteuid().as_raw() {
            return Err(CleanupStatus::Unconfirmed);
        }
        let mut owner = Self {
            path,
            device: metadata.dev(),
            inode: metadata.ino(),
            listener: Some(listener),
            stream: None,
            closed: false,
            cleanup_confirmed: false,
        };
        let permissions =
            std::fs::set_permissions(&owner.path, std::fs::Permissions::from_mode(0o600));
        let verified = std::fs::symlink_metadata(&owner.path).is_ok_and(|metadata| {
            metadata.file_type().is_socket()
                && metadata.uid() == nix::unistd::geteuid().as_raw()
                && metadata.mode() & 0o7777 == 0o600
                && metadata.dev() == owner.device
                && metadata.ino() == owner.inode
        });
        if permissions.is_err() || !verified {
            return Err(if owner.close() {
                CleanupStatus::Confirmed
            } else {
                CleanupStatus::Unconfirmed
            });
        }
        Ok(owner)
    }
    fn close(&mut self) -> bool {
        use std::os::unix::fs::{FileTypeExt, MetadataExt};
        if self.closed {
            return self.cleanup_confirmed;
        }
        self.closed = true;
        drop(self.stream.take());
        drop(self.listener.take());
        let confirmed = match std::fs::symlink_metadata(&self.path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => true,
            Ok(metadata)
                if metadata.file_type().is_socket()
                    && metadata.uid() == nix::unistd::geteuid().as_raw()
                    && metadata.dev() == self.device
                    && metadata.ino() == self.inode =>
            {
                std::fs::remove_file(&self.path).is_ok()
                    && std::fs::symlink_metadata(&self.path)
                        .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound)
            }
            _ => false,
        };
        self.cleanup_confirmed = confirmed;
        confirmed
    }
}
impl Drop for OwnedBridgeSocket {
    fn drop(&mut self) {
        let _ = self.close();
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;
    use std::{fs, time::Duration};
    use uuid::Uuid;

    fn intent() -> RepairRequest {
        RepairRequest::parse(br#"{"schemaVersion":1,"mode":"repair-stranded-authority","expectedInstallationId":"00000000-0000-0000-0000-000000000001","operationId":"original-operation","operatorLabel":"Alice","reason":"reviewed repair","expectedAccessRevision":4,"expectedIdentityId":"00000000-0000-0000-0000-000000000002","responsibility":{"kind":"action-grantor","target":{"kind":"project","projectId":"00000000-0000-0000-0000-000000000003"},"actionId":"edit-project-metadata"}}"#).unwrap()
    }

    fn proof() -> RecipientProof {
        RecipientProof {
            access_token: zeroize::Zeroizing::new("secret-token-sentinel".into()),
            installation_id: Uuid::from_u128(1),
            identity_id: Uuid::from_u128(2),
            principal_id: Uuid::from_u128(10),
        }
    }

    fn fixture() -> (tempfile::TempDir, ExecutionSpec) {
        let directory = tempfile::tempdir().unwrap();
        let script = directory.path().join("maintenance.py");
        fs::write(&script, r"import json, sys
request=json.load(sys.stdin)
assert request['identityProof']=={'kind':'hydra-access-token','accessToken':'secret-token-sentinel'}
assert len(request)==10
sys.stderr.write('secret-token-sentinel')
print(json.dumps({'schemaVersion':1,'mode':request['mode'],'operationId':request['operationId'],'installationId':request['expectedInstallationId'],'principalId':'00000000-0000-0000-0000-00000000000a','accessRevision':request['expectedAccessRevision']+1,'outcome':'repaired','responsibility':request['responsibility']}))
").unwrap();
        let python = std::process::Command::new("python3")
            .args(["-c", "import sys; print(sys.executable)"])
            .output()
            .unwrap();
        assert!(python.status.success());
        let program = String::from_utf8(python.stdout).unwrap().trim().into();
        (
            directory,
            ExecutionSpec {
                program,
                args: vec![script.to_str().unwrap().into()],
                environment: BTreeMap::new(),
            },
        )
    }

    #[tokio::test]
    async fn protected_stdin_and_generated_session_principal_bind_the_original_receipt() {
        let (_directory, execution) = fixture();
        let result = handoff(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            std::future::pending(),
        )
        .await;
        assert!(matches!(result.effect, MaintenanceEffect::Committed { .. }));
        assert_eq!(result.process_cleanup, CleanupStatus::Confirmed);
        assert!(result.failure.is_none());
        assert!(!format!("{result:?}").contains("secret-token-sentinel"));
    }

    #[test]
    fn host_execution_descriptor_is_strict_and_never_resolves_an_ambient_program() {
        let valid=br#"{"program":"/trusted/bin/docker","args":["exec","--interactive","private-backend","inframeld-maintenance"],"environment":{"HOME":"/trusted/empty-home"}}"#;
        assert!(ExecutionSpec::parse(valid).is_ok());
        for invalid in [
            br#"{"program":"docker","args":[]}"#.as_slice(),
            br#"{"program":"/trusted/docker","args":[],"unknown":true}"#.as_slice(),
            br#"{"program":"/trusted/docker","program":"/other/docker","args":[]}"#.as_slice(),
            br#"{"program":"/trusted/docker","args":[],"environment":{"NAME":"first","NAME":"second"}}"#.as_slice(),
            br#"{"program":"/trusted/docker","args":["bad\u0000value"]}"#.as_slice(),
        ] {
            assert!(ExecutionSpec::parse(invalid).is_err());
        }
    }

    #[tokio::test]
    async fn already_cancelled_intent_starts_no_maintenance_process() {
        let (_directory, execution) = fixture();
        let result = handoff(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            std::future::ready(()),
        )
        .await;
        assert!(matches!(result.effect, MaintenanceEffect::NotStarted));
        assert_eq!(result.failure, Some(HandoffFailure::Cancelled));
        assert_eq!(result.process_cleanup, CleanupStatus::NotNeeded);
    }

    fn scripted(tail: &str, keep_receipt: bool) -> (tempfile::TempDir, ExecutionSpec) {
        let (directory, execution) = fixture();
        let script = if keep_receipt {
            format!(
                "{}\nsys.stdout.flush()\n{tail}",
                fs::read_to_string(&execution.args[0]).unwrap()
            )
        } else {
            format!("import json, sys\nrequest=json.load(sys.stdin)\n{tail}")
        };
        fs::write(&execution.args[0], script).unwrap();
        (directory, execution)
    }

    fn short_budgets() -> ProcessBudgets {
        ProcessBudgets {
            execution: Duration::from_millis(120),
            stdin: Duration::from_millis(80),
            term: Duration::from_millis(80),
            kill: Duration::from_secs(2),
        }
    }

    #[tokio::test]
    async fn exit_zero_without_receipt_is_unknown_and_original_operation_is_never_repeated() {
        let (directory, mut execution) =
            scripted("open(sys.argv[1], 'a').write('one effect')", false);
        let marker = directory.path().join("effects");
        execution.args.push(marker.to_str().unwrap().into());
        let result = handoff(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            std::future::pending(),
        )
        .await;
        assert!(
            matches!(&result.effect,MaintenanceEffect::Unknown{operation_id} if operation_id=="original-operation")
        );
        assert_eq!(result.process_cleanup, CleanupStatus::Confirmed);
        assert_eq!(fs::read_to_string(marker).unwrap(), "one effect");
    }

    #[tokio::test]
    async fn cancellation_after_transport_effect_preserves_unknown_commit_and_reaps_once() {
        let (directory, mut execution) = scripted(
            "import time\nwith open(sys.argv[1], 'w') as marker:\n    time.sleep(0.25)\n    marker.write('one effect')\n    marker.flush()\ntime.sleep(30)",
            false,
        );
        let marker = directory.path().join("effects");
        execution.args.push(marker.to_str().unwrap().into());
        let cancelling = async {
            while !fs::read_to_string(&marker).is_ok_and(|value| value == "one effect") {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        };
        let result = handoff(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            cancelling,
        )
        .await;
        let context = format!(
            "failure={:?} cleanup={:?} child_status={:?}",
            result.failure, result.process_cleanup, result.child_status
        );
        assert!(
            matches!(&result.effect,MaintenanceEffect::Unknown{operation_id} if operation_id=="original-operation"),
            "{context}"
        );
        assert_eq!(result.failure, Some(HandoffFailure::Cancelled), "{context}");
        assert_eq!(
            result.process_cleanup,
            CleanupStatus::Confirmed,
            "{context}"
        );
        assert_eq!(
            fs::read_to_string(marker).unwrap(),
            "one effect",
            "{context}"
        );
    }

    #[tokio::test]
    async fn stdout_and_stderr_overflow_remain_bounded_and_never_become_diagnostics() {
        for stream in ["stdout", "stderr"] {
            let (directory, execution) = scripted(
                &format!(
                    "import time\ntime.sleep(0.25)\nsys.{stream}.write('secret-output-sentinel'*4000)\nsys.{stream}.flush()"
                ),
                false,
            );
            let mut budgets = short_budgets();
            budgets.execution = Duration::from_secs(3);
            let result = handoff_with_budgets(
                &execution,
                &intent(),
                &proof(),
                Instant::now() + Duration::from_secs(3),
                std::future::pending(),
                budgets,
            )
            .await;
            let context = format!(
                "stream={stream} failure={:?} cleanup={:?} child_status={:?}",
                result.failure, result.process_cleanup, result.child_status
            );
            assert!(
                matches!(result.effect, MaintenanceEffect::Unknown { .. }),
                "{context}"
            );
            assert_eq!(result.failure, Some(HandoffFailure::Output), "{context}");
            assert_eq!(
                result.process_cleanup,
                CleanupStatus::Confirmed,
                "{context}"
            );
            assert!(
                !format!("{result:?}").contains("secret-output-sentinel"),
                "{context}"
            );
            drop(directory);
        }
    }

    #[tokio::test]
    async fn unreaped_leader_anchors_cleanup_when_descendants_keep_or_close_pipes() {
        for (close_pipes, leader_exits) in [(false, true), (true, true), (false, false)] {
            let tail = format!(
                r"import os, signal, time
time.sleep(0.25)
read_end, write_end=os.pipe()
child=os.fork()
if child==0:
    os.close(read_end)
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    if {close_pipes}:
        os.close(1)
        os.close(2)
    os.write(write_end,b'R')
    os.close(write_end)
    time.sleep(30)
    os._exit(0)
os.close(write_end)
assert os.read(read_end,1)==b'R'
os.close(read_end)
with open(sys.argv[1], 'w') as marker:
    marker.write('ready')
if {leader_exits}:
    os._exit(0)
time.sleep(30)
",
                close_pipes = if close_pipes { "True" } else { "False" },
                leader_exits = if leader_exits { "True" } else { "False" }
            );
            let (directory, mut execution) = scripted(&tail, true);
            let marker = directory.path().join("descendant-ready");
            execution.args.push(marker.to_str().unwrap().into());
            let mut budgets = short_budgets();
            budgets.execution = Duration::from_secs(3);
            let result = handoff_with_budgets(
                &execution,
                &intent(),
                &proof(),
                Instant::now() + Duration::from_secs(3),
                std::future::pending(),
                budgets,
            )
            .await;
            let context = format!(
                "close_pipes={close_pipes} leader_exits={leader_exits} failure={:?} cleanup={:?} child_status={:?}",
                result.failure, result.process_cleanup, result.child_status
            );
            assert!(
                fs::read_to_string(marker).is_ok_and(|value| value == "ready"),
                "descendant readiness was not observed: {context}"
            );
            assert!(
                matches!(result.effect, MaintenanceEffect::Committed { .. }),
                "{context}"
            );
            assert_eq!(
                result.process_cleanup,
                CleanupStatus::Confirmed,
                "{context}"
            );
            if !close_pipes {
                assert_eq!(result.failure, Some(HandoffFailure::TimedOut), "{context}");
            }
        }
    }

    #[tokio::test]
    async fn bound_receipt_survives_explicit_unconfirmed_cleanup_of_an_escaped_descendant() {
        let tail = r"import os, time
time.sleep(0.25)
read_end, write_end=os.pipe()
child=os.fork()
if child==0:
    os.close(read_end)
    os.setsid()
    os.close(1)
    os.write(write_end,b'R')
    os.close(write_end)
    time.sleep(3)
    os._exit(0)
os.close(write_end)
assert os.read(read_end,1)==b'R'
os.close(read_end)
with open(sys.argv[1], 'w') as marker:
    marker.write(f'{child}\n')
    marker.flush()
os._exit(0)
";
        let (directory, mut execution) = scripted(tail, true);
        let marker = directory.path().join("escaped-pid");
        execution.args.push(marker.to_str().unwrap().into());
        let mut budgets = short_budgets();
        budgets.execution = Duration::from_secs(3);
        budgets.kill = Duration::from_millis(40);
        let cancelling = async {
            while !fs::read_to_string(&marker).is_ok_and(|value| {
                value
                    .strip_suffix('\n')
                    .and_then(|pid| pid.parse::<i32>().ok())
                    .is_some_and(|pid| pid > 1)
            }) {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        };
        let result = handoff_with_budgets(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            cancelling,
            budgets,
        )
        .await;
        let pid = fs::read_to_string(marker)
            .ok()
            .and_then(|value| {
                value
                    .strip_suffix('\n')
                    .and_then(|pid| pid.parse::<i32>().ok())
            })
            .filter(|pid| *pid > 1)
            .map(Pid::from_raw);
        // The fixture exits on its own finite timer. Probe only, never signal a
        // numerical PID after the supervisor's ownership has ended.
        let retired = if let Some(pid) = pid {
            tokio::time::timeout(Duration::from_secs(4), async {
                while nix::sys::signal::kill(pid, None) != Err(Errno::ESRCH) {
                    tokio::time::sleep(Duration::from_millis(10)).await;
                }
            })
            .await
            .is_ok()
        } else {
            false
        };
        let context = format!(
            "ready={} retired={retired} failure={:?} cleanup={:?} child_status={:?}",
            pid.is_some(),
            result.failure,
            result.process_cleanup,
            result.child_status
        );
        assert!(
            pid.is_some(),
            "escaped readiness was not observed: {context}"
        );
        assert!(retired, "escaped fixture did not retire: {context}");
        assert!(
            matches!(result.effect, MaintenanceEffect::Committed { .. }),
            "{context}"
        );
        assert_eq!(
            result.process_cleanup,
            CleanupStatus::Unconfirmed,
            "{context}"
        );
    }

    #[tokio::test]
    async fn system_browser_waits_for_detached_ack_eof_before_sending_only_the_url() {
        use super::super::flow::{AuthorizationReady, BrowserLauncher};
        let (directory, execution) = fixture();
        fs::write(
            &execution.args[0],
            r"import json, os, sys
os.setsid()
sys.stdout.write('READY1\n')
sys.stdout.flush()
null=os.open(os.devnull,os.O_RDWR)
os.dup2(null,1)
request=json.load(sys.stdin)
assert set(request)=={'schemaVersion','authorizationUrl'}
assert request['schemaVersion']==1
assert request['authorizationUrl']=='https://identity.test/authorize?state=synthetic-state'
",
        )
        .unwrap();
        let mut browser = SystemBrowser {
            execution,
            used: false,
        };
        let ready = AuthorizationReady {
            authorization_url: url::Url::parse(
                "https://identity.test/authorize?state=synthetic-state",
            )
            .unwrap(),
            issuer: "https://identity.test/".into(),
            callback_uri: "http://127.0.0.1:49152/expected".into(),
        };
        let mut cancellation = std::pin::pin!(std::future::pending::<()>());
        let result = browser
            .open(
                &ready,
                Instant::now() + Duration::from_secs(3),
                cancellation.as_mut(),
            )
            .await;
        assert!(result.is_ok(), "{result:?}");
        drop(directory);
    }

    #[test]
    fn interrupted_exit_observation_keeps_the_unreaped_owner_for_bounded_cleanup() {
        let mut anchor = ProcessAnchor {
            pid: None,
            observed: None,
            outcome: ChildStatus::Unobserved,
            ownership: LeaderOwnership::Retained,
            group_owned: true,
        };
        assert!(matches!(
            anchor.record_observation(Err(rustix::io::Errno::INTR)),
            Ok(None)
        ));
        assert!(anchor.ownership == LeaderOwnership::Retained);
        assert!(
            anchor
                .record_observation(Err(rustix::io::Errno::CHILD))
                .is_err()
        );
        assert!(anchor.ownership == LeaderOwnership::Lost);
    }

    struct InterruptedReader(u8);
    impl tokio::io::AsyncRead for InterruptedReader {
        fn poll_read(
            self: std::pin::Pin<&mut Self>,
            _context: &mut std::task::Context<'_>,
            buffer: &mut tokio::io::ReadBuf<'_>,
        ) -> std::task::Poll<std::io::Result<()>> {
            let this = self.get_mut();
            let step = this.0;
            this.0 += 1;
            std::task::Poll::Ready(match step {
                0 => Err(std::io::ErrorKind::Interrupted.into()),
                1 => {
                    buffer.put_slice(b"private-output-sentinel");
                    Ok(())
                }
                _ => Ok(()),
            })
        }
    }
    #[tokio::test]
    async fn interrupted_pipe_read_keeps_draining_without_false_eof_or_disclosure() {
        let mut output = BoundedOutput::new(Some(InterruptedReader(0)), 128, true);
        assert!(output.collect().await.is_ok());
        assert!(output.complete);
        assert!(!output.failed);
        assert_eq!(output.bytes.as_slice(), b"private-output-sentinel");
    }

    fn navigation() -> super::super::flow::AuthorizationReady {
        super::super::flow::AuthorizationReady {
            authorization_url: url::Url::parse(
                "https://identity.test/authorize?state=synthetic-state",
            )
            .unwrap(),
            issuer: "https://identity.test/".into(),
            callback_uri: "http://127.0.0.1:49152/expected".into(),
        }
    }

    #[tokio::test]
    async fn browser_never_admits_url_before_exact_detached_ack_and_eof() {
        use super::super::flow::{BrowserFailureKind, BrowserLauncher};
        for (detach, ack, close_ack) in [
            (true, "READY1\n", false),
            (true, "WRONG\n", true),
            (false, "READY1\n", true),
        ] {
            let (directory, mut execution) = fixture();
            let marker = directory.path().join("url-admitted");
            execution.args.push(marker.to_str().unwrap().into());
            fs::write(
                &execution.args[0],
                format!(
                    r"import os, sys
{detach}
sys.stdout.write({ack})
sys.stdout.flush()
{close_ack}
if sys.stdin.read():
    open(sys.argv[1],'w').write('unexpected admission')
",
                    detach = if detach { "os.setsid()" } else { "pass" },
                    ack = serde_json::to_string(ack).unwrap(),
                    close_ack = if close_ack {
                        "null=os.open(os.devnull,os.O_RDWR); os.dup2(null,1)"
                    } else {
                        "pass"
                    }
                ),
            )
            .unwrap();
            let mut browser = SystemBrowser {
                execution,
                used: false,
            };
            let mut cancellation = std::pin::pin!(std::future::pending::<()>());
            let error = browser
                .open(
                    &navigation(),
                    Instant::now() + Duration::from_millis(150),
                    cancellation.as_mut(),
                )
                .await
                .unwrap_err();
            assert_eq!(
                error.kind,
                if close_ack {
                    BrowserFailureKind::Failed
                } else {
                    BrowserFailureKind::TimedOut
                }
            );
            assert_eq!(error.resource_cleanup, CleanupStatus::Confirmed);
            assert!(!marker.exists());
        }
    }

    #[tokio::test]
    async fn browser_cancellation_before_and_after_ack_awaits_the_owned_finalizer() {
        use super::super::flow::{BrowserFailureKind, BrowserLauncher};
        for after_ack in [false, true] {
            let (directory, mut execution) = fixture();
            let marker = directory.path().join("cancel-now");
            execution.args.push(marker.to_str().unwrap().into());
            fs::write(&execution.args[0],format!(r"import json, os, sys, time
os.setsid()
{handshake}
open(sys.argv[1],'w').write('ready')
time.sleep(30)
",handshake=if after_ack {"sys.stdout.write('READY1\\n'); sys.stdout.flush(); null=os.open(os.devnull,os.O_RDWR); os.dup2(null,1); json.load(sys.stdin)"}else{"pass"})).unwrap();
            let mut browser = SystemBrowser {
                execution,
                used: false,
            };
            let mut cancellation = std::pin::pin!(async {
                while !marker.exists() {
                    tokio::time::sleep(Duration::from_millis(5)).await;
                }
            });
            let error = browser
                .open(
                    &navigation(),
                    Instant::now() + Duration::from_secs(1),
                    cancellation.as_mut(),
                )
                .await
                .unwrap_err();
            assert_eq!(
                error.kind,
                BrowserFailureKind::Cancelled,
                "after_ack={after_ack}"
            );
            assert_eq!(error.resource_cleanup, CleanupStatus::Confirmed);
        }
    }

    #[tokio::test]
    async fn protected_bridge_preserves_unsafe_parents_existing_entries_and_replacements() {
        use std::os::unix::fs::PermissionsExt;
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("browser.sock");
        fs::set_permissions(directory.path(), fs::Permissions::from_mode(0o755)).unwrap();
        assert!(matches!(
            OwnedBridgeSocket::bind(path.clone()),
            Err(CleanupStatus::NotNeeded)
        ));
        assert!(!path.exists());
        fs::set_permissions(directory.path(), fs::Permissions::from_mode(0o700)).unwrap();
        fs::write(&path, "pre-existing").unwrap();
        assert!(matches!(
            OwnedBridgeSocket::bind(path.clone()),
            Err(CleanupStatus::NotNeeded)
        ));
        assert_eq!(fs::read_to_string(&path).unwrap(), "pre-existing");
        fs::remove_file(&path).unwrap();
        let mut owner = OwnedBridgeSocket::bind(path.clone()).unwrap();
        fs::remove_file(&path).unwrap();
        fs::write(&path, "replacement").unwrap();
        assert!(!owner.close());
        assert_eq!(fs::read_to_string(&path).unwrap(), "replacement");
    }

    #[tokio::test]
    async fn bridge_cancellation_closes_and_unlinks_once_without_retry_or_replay() {
        use super::super::flow::{BrowserFailureKind, BrowserLauncher};
        use std::os::unix::fs::PermissionsExt;
        let directory = tempfile::tempdir().unwrap();
        fs::set_permissions(directory.path(), fs::Permissions::from_mode(0o700)).unwrap();
        let path = directory.path().join("browser.sock");
        let mut bridge = NativeBrowserBridge::new(path.clone());
        let mut cancellation = std::pin::pin!(async {
            while !path.exists() {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        });
        let error = bridge
            .open(
                &navigation(),
                Instant::now() + Duration::from_secs(1),
                cancellation.as_mut(),
            )
            .await
            .unwrap_err();
        assert_eq!(error.kind, BrowserFailureKind::Cancelled);
        assert_eq!(error.resource_cleanup, CleanupStatus::Confirmed);
        assert!(!path.exists());
        let mut uncancelled = std::pin::pin!(std::future::pending::<()>());
        assert!(
            bridge
                .open(
                    &navigation(),
                    Instant::now() + Duration::from_secs(1),
                    uncancelled.as_mut()
                )
                .await
                .is_err()
        );
        assert!(!path.exists());
    }

    #[tokio::test]
    async fn blocked_stdin_is_bounded_and_closes_the_protected_writer_on_timeout() {
        let (writer, mut peer) = tokio::io::duplex(8);
        let result = write_child_input(
            writer,
            b"protected-synthetic-input",
            Instant::now() + Duration::from_secs(1),
            Duration::from_millis(10),
        )
        .await;
        assert_eq!(result, Err(HandoffFailure::Input));
        let mut remaining = Vec::new();
        tokio::time::timeout(Duration::from_millis(100), peer.read_to_end(&mut remaining))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(remaining, b"protecte");
    }

    #[tokio::test]
    async fn recipient_diagnostic_retains_bound_error_and_actual_child_exit_without_raw_output() {
        let (_directory, execution) = scripted(
            "print(json.dumps({'schemaVersion':1,'operationId':request['operationId'],'code':'stale_revision'}))\nsys.stderr.write('protected-stderr-sentinel')\nsys.exit(7)",
            false,
        );
        let result = handoff(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            std::future::pending(),
        )
        .await;
        assert_eq!(result.process_cleanup, CleanupStatus::Confirmed);
        assert_eq!(result.failure, Some(HandoffFailure::Exit));
        assert!(
            matches!(&result.effect, MaintenanceEffect::Unknown { operation_id } if operation_id=="original-operation")
        );
        assert_eq!(result.child_status, ChildStatus::Exited(7));
        assert_eq!(
            result.backend_error,
            Some(MaintenanceErrorCode::StaleRevision)
        );
        assert!(!format!("{result:?}").contains("protected-stderr-sentinel"));
        assert!(
            !serde_json::to_string(&result)
                .unwrap()
                .contains("childStatus")
        );
    }

    #[tokio::test]
    async fn recipient_diagnostic_distinguishes_signal_from_an_exit_code() {
        let (_directory, execution) = scripted(
            "import os, signal\nos.kill(os.getpid(), signal.SIGTERM)",
            false,
        );
        let result = handoff(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            std::future::pending(),
        )
        .await;
        assert_eq!(result.process_cleanup, CleanupStatus::Confirmed);
        assert_eq!(result.failure, Some(HandoffFailure::Exit));
        assert_eq!(result.child_status, ChildStatus::Signaled(15));
        assert_eq!(result.backend_error, None);
    }

    #[tokio::test]
    async fn recipient_diagnostic_keeps_timeout_as_original_cause_after_finalizer_signal() {
        let (_directory, execution) = scripted("import time\ntime.sleep(30)", false);
        let result = handoff_with_budgets(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            std::future::pending(),
            short_budgets(),
        )
        .await;
        assert_eq!(result.process_cleanup, CleanupStatus::Confirmed);
        assert_eq!(result.failure, Some(HandoffFailure::TimedOut));
        assert_eq!(result.child_status, ChildStatus::Signaled(15));
        assert!(matches!(result.effect, MaintenanceEffect::Unknown { .. }));
    }

    #[tokio::test]
    async fn recipient_diagnostic_keeps_committed_receipt_despite_later_nonzero_exit() {
        let (_directory, execution) = scripted("sys.exit(7)", true);
        let result = handoff(
            &execution,
            &intent(),
            &proof(),
            Instant::now() + Duration::from_secs(3),
            std::future::pending(),
        )
        .await;
        assert_eq!(result.process_cleanup, CleanupStatus::Confirmed);
        assert_eq!(result.failure, Some(HandoffFailure::Exit));
        assert!(matches!(result.effect, MaintenanceEffect::Committed { .. }));
        assert_eq!(result.child_status, ChildStatus::Exited(7));
        assert_eq!(result.backend_error, None);
    }
}
