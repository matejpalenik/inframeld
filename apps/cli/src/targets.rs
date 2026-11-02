//! Retain credential-free target bindings and explicit local preferences.

use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions, TryLockError},
    io::{Read, Write},
    os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU8, Ordering},
    time::{Duration, Instant},
};

use rustls::pki_types::{CertificateDer, pem::PemObject};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::discovery::{DiscoveryError, DiscoveryOptions};

const REGISTRY_LIMIT: usize = 4 * 1024 * 1024;
const CA_LIMIT: usize = 256 * 1024;

/// Explicit operator-managed trust inputs, separate from installation identity.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct Transport {
    pub ca_files: Vec<PathBuf>,
    pub proxy: Option<String>,
}

impl Transport {
    pub(crate) fn new(ca_files: Vec<PathBuf>, proxy: Option<String>) -> Result<Self, TargetError> {
        let ca_files = ca_files
            .into_iter()
            .map(|path| std::path::absolute(path).map_err(|_| TargetError::InvalidCa))
            .collect::<Result<Vec<_>, _>>()?;
        let transport = Self { ca_files, proxy };
        transport.validate()?;
        Ok(transport)
    }

    /// Snapshot live operator CA files once for this transport, without copying them to user state.
    pub(crate) fn options(&self) -> Result<DiscoveryOptions, TargetError> {
        self.validate()?;
        let mut certificates = Vec::new();
        for path in &self.ca_files {
            // Refuse a named pipe or device before an ordinary read-only open
            // can wait for an unrelated producer.
            if !fs::metadata(path)
                .map_err(|_| TargetError::InvalidCa)?
                .is_file()
            {
                return Err(TargetError::InvalidCa);
            }
            let file = File::open(path).map_err(|_| TargetError::InvalidCa)?;
            if !file
                .metadata()
                .map_err(|_| TargetError::InvalidCa)?
                .is_file()
            {
                return Err(TargetError::InvalidCa);
            }
            let mut bytes = Vec::new();
            file.take(CA_LIMIT as u64 + 1)
                .read_to_end(&mut bytes)
                .map_err(|_| TargetError::InvalidCa)?;
            if bytes.len() > CA_LIMIT
                || bytes
                    .windows(b"PRIVATE KEY".len())
                    .any(|window| window == b"PRIVATE KEY")
            {
                return Err(TargetError::InvalidCa);
            }
            let parsed = CertificateDer::pem_slice_iter(&bytes)
                .collect::<Result<Vec<_>, _>>()
                .map_err(|_| TargetError::InvalidCa)?;
            if parsed.is_empty() {
                return Err(TargetError::InvalidCa);
            }
            let mut validation = rustls::RootCertStore::empty();
            for certificate in parsed {
                validation
                    .add(certificate.clone())
                    .map_err(|_| TargetError::InvalidCa)?;
                certificates.push(
                    reqwest::Certificate::from_der(certificate.as_ref())
                        .map_err(|_| TargetError::InvalidCa)?,
                );
            }
        }
        let proxy = self
            .proxy
            .as_deref()
            .map(reqwest::Proxy::all)
            .transpose()
            .map_err(|_| TargetError::InvalidProxy)?;
        Ok(DiscoveryOptions {
            certificate_authorities: certificates,
            proxy,
        })
    }

    fn validate(&self) -> Result<(), TargetError> {
        if let Some(value) = &self.proxy {
            let url = url::Url::parse(value).map_err(|_| TargetError::InvalidProxy)?;
            let authority = value
                .split_once("://")
                .map(|(_, rest)| rest.split(['/', '?', '#']).next().unwrap_or(""));
            if value.len() > 8192
                || !matches!(url.scheme(), "http" | "https")
                || url.host_str().is_none()
                || !url.username().is_empty()
                || url.password().is_some()
                || authority.is_none_or(|part| part.contains('@'))
                || url.query().is_some()
                || url.fragment().is_some()
                || url.path() != "/"
                || value.chars().any(|c| c.is_control() || c.is_whitespace())
                || value.contains('\\')
            {
                return Err(TargetError::InvalidProxy);
            }
        }
        if self.ca_files.len() > 8
            || self.ca_files.iter().any(|path| {
                !path.is_absolute()
                    || path
                        .to_str()
                        .is_none_or(|text| text.len() > 4096 || text.chars().any(char::is_control))
            })
        {
            return Err(TargetError::InvalidCa);
        }
        Ok(())
    }
}

/// Public discovery facts saved without account or credential state.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct Target {
    pub label: String,
    pub installation_id: Uuid,
    pub api_url: String,
    pub issuer_url: String,
    pub client_id: String,
    pub transport: Transport,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct State {
    pub schema_version: u8,
    pub selected_target: Option<String>,
    pub targets: BTreeMap<String, Target>,
}

impl Default for State {
    fn default() -> Self {
        Self {
            schema_version: 1,
            selected_target: None,
            targets: BTreeMap::new(),
        }
    }
}

impl State {
    fn validate(&self) -> Result<(), TargetError> {
        if self.schema_version != 1
            || self
                .selected_target
                .as_ref()
                .is_some_and(|name| !self.targets.contains_key(name))
        {
            return Err(TargetError::InvalidState);
        }
        for (label, target) in &self.targets {
            if label != &target.label {
                return Err(TargetError::InvalidState);
            }
            target.validate().map_err(|_| TargetError::InvalidState)?;
        }
        Ok(())
    }
}

impl Target {
    fn validate(&self) -> Result<(), TargetError> {
        validate_label(&self.label)?;
        if self.client_id != "inframeld-cli" {
            return Err(TargetError::InvalidState);
        }
        crate::discovery::validate_saved_identity(&self.api_url, &self.issuer_url)?;
        self.transport.validate()
    }
}

#[derive(Debug)]
pub(crate) enum Change {
    Register(Target),
    Select(String),
}

/// A confirmed complete state after a guarded update.
#[derive(Debug)]
pub(crate) struct Update {
    pub state: State,
    pub changed: bool,
    /// The observed preference from the reload under the writer lock.
    pub previous_selected_target: Option<String>,
}

/// One user's target registry. A separate persistent inode owns writer exclusion.
#[derive(Debug)]
pub(crate) struct Store {
    pub directory: PathBuf,
}

impl Store {
    pub(crate) fn from_environment() -> Result<Self, TargetError> {
        let root = match std::env::var_os("XDG_CONFIG_HOME") {
            Some(value) => PathBuf::from(value),
            None => PathBuf::from(std::env::var_os("HOME").ok_or(TargetError::Io)?).join(".config"),
        };
        if !root.is_absolute() {
            return Err(TargetError::InvalidState);
        }
        Ok(Self {
            directory: root.join("inframeld"),
        })
    }

    pub(crate) fn load(&self) -> Result<State, TargetError> {
        match fs::symlink_metadata(&self.directory) {
            Ok(_) => private_directory(&self.directory)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(State::default());
            }
            Err(_) => return Err(TargetError::Io),
        }
        let path = self.directory.join("targets");
        match fs::symlink_metadata(&path) {
            Ok(metadata) if metadata.is_file() && private_permissions(&metadata) => {}
            Ok(_) => return Err(TargetError::InvalidState),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(State::default());
            }
            Err(_) => return Err(TargetError::Io),
        }
        let file = File::open(path).map_err(|_| TargetError::Io)?;
        let mut bytes = Vec::new();
        file.take(REGISTRY_LIMIT as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| TargetError::Io)?;
        if bytes.len() > REGISTRY_LIMIT {
            return Err(TargetError::InvalidState);
        }
        let state: State = serde_json::from_slice(&bytes).map_err(|_| TargetError::InvalidState)?;
        state.validate()?;
        Ok(state)
    }

    /// Serialize only local updates. Discovery and other external work never hold this lock.
    pub(crate) async fn update(
        &self,
        change: Change,
        stop: &AtomicU8,
    ) -> Result<Update, TargetError> {
        stopped(stop)?;
        match &change {
            Change::Register(target) => target.validate()?,
            Change::Select(label) => validate_label(label)?,
        }
        fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(&self.directory)
            .map_err(|_| TargetError::Io)?;
        private_directory(&self.directory)?;
        let path = self.directory.join("targets.lock");
        if let Ok(metadata) = fs::symlink_metadata(&path)
            && (!metadata.is_file() || !private_permissions(&metadata))
        {
            return Err(TargetError::InvalidState);
        }
        let lock = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .truncate(false)
            .mode(0o600)
            .open(path)
            .map_err(|_| TargetError::Io)?;
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            stopped(stop)?;
            match lock.try_lock() {
                Ok(()) => break,
                Err(TryLockError::WouldBlock) if Instant::now() < deadline => {
                    tokio::time::sleep(Duration::from_millis(25)).await;
                }
                Err(TryLockError::WouldBlock) => return Err(TargetError::Busy),
                Err(TryLockError::Error(_)) => return Err(TargetError::Io),
            }
        }
        let mut state = self.load()?;
        let previous_selected_target = state.selected_target.clone();
        let changed = match change {
            Change::Register(target) => match state.targets.get(&target.label) {
                Some(existing) if existing == &target => false,
                Some(_) => return Err(TargetError::Conflict),
                None => {
                    state.targets.insert(target.label.clone(), target);
                    true
                }
            },
            Change::Select(label) => {
                if !state.targets.contains_key(&label) {
                    return Err(TargetError::NotFound);
                }
                let changed = state.selected_target.as_ref() != Some(&label);
                state.selected_target = Some(label);
                changed
            }
        };
        stopped(stop)?;
        if changed {
            publish(&self.directory, &state, |directory| {
                File::open(directory)?.sync_all()
            })?;
        }
        Ok(Update {
            state,
            changed,
            previous_selected_target,
        })
    }
}

// Keep the Unix group/other permission mask visible at the trust boundary.
#[allow(clippy::verbose_bit_mask)]
fn private_permissions(metadata: &fs::Metadata) -> bool {
    metadata.permissions().mode() & 0o077 == 0
}

fn private_directory(path: &Path) -> Result<(), TargetError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| TargetError::Io)?;
    if !metadata.is_dir() || !private_permissions(&metadata) {
        return Err(TargetError::InvalidState);
    }
    Ok(())
}

fn stopped(stop: &AtomicU8) -> Result<(), TargetError> {
    if stop.load(Ordering::Acquire) == 0 {
        Ok(())
    } else {
        Err(TargetError::Interrupted)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum SelectionSource {
    Flag,
    Environment,
    Saved,
}

pub(crate) fn resolve(
    state: &State,
    explicit: Option<&str>,
    environment: Option<&str>,
) -> Result<(Target, SelectionSource), TargetError> {
    let (label, source) = if let Some(label) = explicit {
        (label, SelectionSource::Flag)
    } else if let Some(label) = environment {
        (label, SelectionSource::Environment)
    } else {
        (
            state
                .selected_target
                .as_deref()
                .ok_or(TargetError::NotFound)?,
            SelectionSource::Saved,
        )
    };
    validate_label(label)?;
    Ok((
        state
            .targets
            .get(label)
            .ok_or(TargetError::NotFound)?
            .clone(),
        source,
    ))
}

pub(crate) fn validate_label(label: &str) -> Result<(), TargetError> {
    if label.is_empty()
        || label.len() > 64
        || !label.as_bytes()[0].is_ascii_alphanumeric()
        || !label
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'.' | b'_' | b'-'))
    {
        return Err(TargetError::InvalidLabel);
    }
    Ok(())
}

fn publish(
    directory: &Path,
    state: &State,
    sync_parent: impl FnOnce(&Path) -> std::io::Result<()>,
) -> Result<(), TargetError> {
    let bytes = serde_json::to_vec_pretty(state).map_err(|_| TargetError::InvalidState)?;
    if bytes.len() >= REGISTRY_LIMIT {
        return Err(TargetError::InvalidState);
    }
    let mut temporary = tempfile::NamedTempFile::new_in(directory).map_err(|_| TargetError::Io)?;
    temporary
        .as_file()
        .set_permissions(fs::Permissions::from_mode(0o600))
        .map_err(|_| TargetError::Io)?;
    temporary
        .write_all(&bytes)
        .and_then(|()| temporary.write_all(b"\n"))
        .and_then(|()| temporary.as_file().sync_all())
        .map_err(|_| TargetError::Io)?;
    temporary
        .persist(directory.join("targets"))
        .map_err(|_| TargetError::Uncertain)?;
    sync_parent(directory).map_err(|_| TargetError::Uncertain)
}

/// Safe local failures never retain file contents, submitted URLs or vendor text.
#[derive(Debug, thiserror::Error)]
pub(crate) enum TargetError {
    #[error(
        "Provide a target label of 1-64 ASCII letters, digits, dots, underscores or hyphens, starting with a letter or digit."
    )]
    InvalidLabel,
    #[error(
        "The saved target registry is malformed, unsupported or insecure. Preserve it and inspect the documented target configuration."
    )]
    InvalidState,
    #[error("The target registry could not be read or saved.")]
    Io,
    #[error("Another target update is in progress. No change was saved by this invocation.")]
    Busy,
    #[error(
        "That label already has a different binding. Choose a new label. Existing targets and selections were preserved."
    )]
    Conflict,
    #[error("The selected target is not registered. Register it explicitly with target add.")]
    NotFound,
    #[error("Provide readable public PEM CA files within the documented limits.")]
    InvalidCa,
    #[error(
        "Provide a credential-free HTTP(S) proxy origin without a query, fragment or user information."
    )]
    InvalidProxy,
    /// A URL rejected from the caller's explicit input, before discovery dispatch.
    #[error("{0}")]
    InvalidApiUrl(DiscoveryError),
    #[error("The target command was interrupted. Confirm saved state with target show.")]
    Interrupted,
    #[error(
        "Target persistence could not be confirmed. Inspect the target registry before repeating the change."
    )]
    Uncertain,
    #[error("{0}")]
    Discovery(#[from] DiscoveryError),
}

impl TargetError {
    pub(crate) fn code(&self) -> &'static str {
        match self {
            Self::InvalidLabel => "invalid_target_label",
            Self::InvalidState => "invalid_target_state",
            Self::Io => "target_state_io",
            Self::Busy => "target_state_busy",
            Self::Conflict => "target_binding_conflict",
            Self::NotFound => "target_not_found",
            Self::InvalidCa => "invalid_ca_file",
            Self::InvalidProxy => "invalid_proxy_url",
            Self::Interrupted => "target_interrupted",
            Self::Uncertain => "target_write_uncertain",
            Self::InvalidApiUrl(error) | Self::Discovery(error) => match error {
                DiscoveryError::InvalidUrl => "discovery_invalid_url",
                DiscoveryError::IdentityMismatch => "discovery_identity_mismatch",
                DiscoveryError::InvalidMetadata => "discovery_invalid_metadata",
                DiscoveryError::UnsupportedProfile => "discovery_unsupported_profile",
                DiscoveryError::Unavailable => "discovery_unavailable",
                DiscoveryError::Tls => "discovery_tls",
                DiscoveryError::Redirect => "discovery_redirect",
                DiscoveryError::ResponseTooLarge => "discovery_response_too_large",
                DiscoveryError::Timeout => "discovery_timeout",
                DiscoveryError::Transport => "discovery_transport",
            },
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;
    use std::{fs, os::unix::fs::PermissionsExt, sync::atomic::AtomicU8};
    use tempfile::TempDir;

    fn target(label: &str) -> Target {
        Target {
            label: label.into(),
            installation_id: Uuid::from_u128(42),
            api_url: "https://api.example.test/api/v1".into(),
            issuer_url: "https://identity.example.test".into(),
            client_id: "inframeld-cli".into(),
            transport: Transport::default(),
        }
    }

    fn store(home: &TempDir) -> Store {
        Store {
            directory: home.path().join("inframeld"),
        }
    }

    #[tokio::test]
    async fn registration_and_selection_preserve_independent_targets() {
        let home = TempDir::new().unwrap();
        let store = store(&home);
        let stop = AtomicU8::new(0);
        let registered = store
            .update(Change::Register(target("dev")), &stop)
            .await
            .unwrap();
        assert!(registered.changed && registered.state.selected_target.is_none());
        store
            .update(Change::Register(target("prod")), &stop)
            .await
            .unwrap();
        store
            .update(Change::Select("dev".into()), &stop)
            .await
            .unwrap();
        let state = store.load().unwrap();
        assert_eq!(state.selected_target.as_deref(), Some("dev"));
        assert_eq!(state.targets.len(), 2);
        assert_eq!(
            fs::metadata(&store.directory).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(store.directory.join("targets"))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }

    #[tokio::test]
    async fn conflicting_rebind_does_not_replace_a_target_or_its_preference() {
        let home = TempDir::new().unwrap();
        let store = store(&home);
        let stop = AtomicU8::new(0);
        store
            .update(Change::Register(target("dev")), &stop)
            .await
            .unwrap();
        store
            .update(Change::Select("dev".into()), &stop)
            .await
            .unwrap();
        let before = fs::read(store.directory.join("targets")).unwrap();
        let mut different = target("dev");
        different.installation_id = Uuid::from_u128(43);
        assert!(matches!(
            store.update(Change::Register(different), &stop).await,
            Err(TargetError::Conflict)
        ));
        assert_eq!(fs::read(store.directory.join("targets")).unwrap(), before);
    }

    #[test]
    fn explicit_selection_ignores_invalid_lower_priority_values() {
        let state = State {
            selected_target: Some("prod".into()),
            targets: [
                ("dev".into(), target("dev")),
                ("prod".into(), target("prod")),
            ]
            .into(),
            ..State::default()
        };
        let (selected, source) = resolve(&state, Some("dev"), Some("https://not-a-label")).unwrap();
        assert_eq!(
            (selected.label.as_str(), source),
            ("dev", SelectionSource::Flag)
        );
        assert!(matches!(
            resolve(&state, None, Some(" ")),
            Err(TargetError::InvalidLabel)
        ));
        assert_eq!(resolve(&state, None, None).unwrap().0.label, "prod");
    }

    #[test]
    fn labels_and_explicit_credential_free_proxy_are_validated_without_network() {
        assert!(validate_label("dev-1.A").is_ok());
        assert!(validate_label("https://api.test").is_err());
        assert!(Transport::new(vec![], Some("http://proxy.example.test:8080".into())).is_ok());
        for value in [
            "http://@proxy.test",
            "http://user:private@proxy.test",
            "http://%75ser@proxy.test",
            "http://proxy.test?private=value",
        ] {
            assert!(matches!(
                Transport::new(vec![], Some(value.into())),
                Err(TargetError::InvalidProxy)
            ));
        }
    }

    #[test]
    fn operator_ca_reference_is_absolute_and_is_reread_for_each_attempt() {
        let home = TempDir::new().unwrap();
        let path = home.path().join("operator.pem");
        let certified = rcgen::generate_simple_self_signed(vec!["localhost".into()]).unwrap();
        fs::write(&path, certified.cert.pem()).unwrap();
        let transport = Transport::new(vec![path.clone()], None).unwrap();
        assert_eq!(transport.ca_files, std::slice::from_ref(&path));
        assert_eq!(
            transport.options().unwrap().certificate_authorities.len(),
            1
        );
        fs::write(&path, "not a certificate").unwrap();
        assert!(matches!(transport.options(), Err(TargetError::InvalidCa)));
    }

    #[test]
    fn a_pem_envelope_with_invalid_certificate_bytes_is_a_ca_input_error() {
        let home = TempDir::new().unwrap();
        let path = home.path().join("operator.pem");
        fs::write(
            &path,
            "-----BEGIN CERTIFICATE-----\nAQID\n-----END CERTIFICATE-----\n",
        )
        .unwrap();
        let transport = Transport::new(vec![path], None).unwrap();
        assert!(matches!(transport.options(), Err(TargetError::InvalidCa)));
    }

    #[tokio::test]
    async fn already_observed_stop_prevents_creating_user_state() {
        let home = TempDir::new().unwrap();
        let store = store(&home);
        assert!(matches!(
            store
                .update(Change::Register(target("dev")), &AtomicU8::new(130))
                .await,
            Err(TargetError::Interrupted)
        ));
        assert!(!store.directory.exists());
    }

    #[test]
    fn malformed_saved_state_is_rejected_without_rewriting_it() {
        let home = TempDir::new().unwrap();
        let store = store(&home);
        fs::create_dir(&store.directory).unwrap();
        fs::set_permissions(&store.directory, fs::Permissions::from_mode(0o700)).unwrap();
        let path = store.directory.join("targets");
        fs::write(&path, "private malformed state").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(matches!(store.load(), Err(TargetError::InvalidState)));
        assert_eq!(fs::read_to_string(path).unwrap(), "private malformed state");
    }

    #[tokio::test]
    async fn another_kernel_lock_owner_prevents_an_update_within_the_bound() {
        use std::os::unix::fs::OpenOptionsExt;
        let home = TempDir::new().unwrap();
        let store = store(&home);
        fs::create_dir(&store.directory).unwrap();
        fs::set_permissions(&store.directory, fs::Permissions::from_mode(0o700)).unwrap();
        let lock = fs::OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .truncate(false)
            .mode(0o600)
            .open(store.directory.join("targets.lock"))
            .unwrap();
        lock.lock().unwrap();
        let started = std::time::Instant::now();
        assert!(matches!(
            store
                .update(Change::Register(target("dev")), &AtomicU8::new(0))
                .await,
            Err(TargetError::Busy)
        ));
        assert!(started.elapsed() < std::time::Duration::from_secs(3));
        assert!(!store.directory.join("targets").exists());
    }

    #[test]
    fn directory_sync_failure_retains_the_published_bytes_and_reports_uncertainty() {
        let home = TempDir::new().unwrap();
        let state = State {
            targets: [("dev".into(), target("dev"))].into(),
            ..State::default()
        };
        let result = publish(home.path(), &state, |_| {
            Err(std::io::ErrorKind::PermissionDenied.into())
        });
        assert!(matches!(result, Err(TargetError::Uncertain)));
        let persisted: State =
            serde_json::from_slice(&fs::read(home.path().join("targets")).unwrap()).unwrap();
        assert_eq!(persisted.targets["dev"], target("dev"));
    }

    #[tokio::test]
    async fn selection_observation_comes_from_the_reload_after_acquiring_the_kernel_lock() {
        let home = TempDir::new().unwrap();
        let store = store(&home);
        let stop = AtomicU8::new(0);
        for label in ["dev", "prod"] {
            store
                .update(Change::Register(target(label)), &stop)
                .await
                .unwrap();
        }
        store
            .update(Change::Select("dev".into()), &stop)
            .await
            .unwrap();
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .open(store.directory.join("targets.lock"))
            .unwrap();
        lock.lock().unwrap();
        let mut waiting = Box::pin(store.update(Change::Select("dev".into()), &stop));
        let early = tokio::select! {
            result = &mut waiting => Some(result),
            () = tokio::time::sleep(Duration::from_millis(30)) => None,
        };
        assert!(
            early.is_none(),
            "The existing kernel lock must exclude the waiting writer."
        );
        let mut intervening = store.load().unwrap();
        intervening.selected_target = Some("prod".into());
        publish(&store.directory, &intervening, |path| {
            File::open(path)?.sync_all()
        })
        .unwrap();
        lock.unlock().unwrap();
        let update = waiting.await.unwrap();
        assert_eq!(update.previous_selected_target.as_deref(), Some("prod"));
        assert_eq!(update.state.selected_target.as_deref(), Some("dev"));
        assert!(update.changed);
    }
}
