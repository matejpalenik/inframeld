# Follow a bounded artifact check through complete Rust components

Alice wants to check a downloaded archive against a checksum supplied by an explicitly trusted source. The check must reject malformed expectations, excessive data, mismatched content and read failures. It must not execute or extract the archive. This original teaching example shows a meaningful value, stateless operation, standard-library capability and concrete file adapter without introducing a service framework.

> **Status:** illustrative new files, not a replacement for the existing xtask or a delivered CLI command. The temporary qualification crate uses the library name `inframeld_cli_xtask` so the doctest's imports match the proposed destination. Actual packaging additionally checks archive shape, metadata, native execution and provenance limits under the existing [CLI guide](../../../../apps/cli/README.md). This checksum check alone cannot establish those guarantees.

## Responsibilities and placement

The proposed files below would form `apps/cli/xtask/src/checksum/`. The facade keeps implementations private and exposes the meaningful value, operations and outcomes. The digest owns parsing and canonical display. Verification uses `std::io::Read`, so it needs neither a filesystem dependency nor a custom reader protocol. The file adapter opens and owns the concrete resource.

This is the capability pattern from [module design](module-design.md). The related result and error share the verification module because they describe that operation. There is no requirement to give each declaration a file or a trait. The byte budget is an explicit input in this teaching API. Actual application policy decides its approved value.

Each block is the complete content of the named illustrative new file. To integrate the example, insert `pub mod checksum;` after the existing `pub mod archive;` declaration in `apps/cli/xtask/src/lib.rs`. This document does not apply that insertion. Dependencies are the existing xtask `sha2` and `thiserror` libraries, with the pinned toolchain and authored-code lints.

### `apps/cli/xtask/src/checksum/mod.rs`

```rust
//! Check bounded artifact bytes against a caller-supplied SHA-256 digest.
//!
//! Use [`ArtifactDigest`] to validate expected text, then [`verify_reader`]
//! for an existing reader or [`verify_file`] for a local file. Success covers
//! the bytes read, not publisher identity, safe extraction or a future reread.

mod digest;
mod file;
mod verify;

pub use digest::{ArtifactDigest, InvalidDigest};
pub use file::verify_file;
pub use verify::{VerificationError, VerifiedArtifact, verify_reader};
```

### `apps/cli/xtask/src/checksum/digest.rs`

```rust
//! Represent a complete SHA-256 value separately from unvalidated text.

use std::fmt;

/// A parsed SHA-256 digest, displayed as 64 lowercase hexadecimal characters.
///
/// Parsing accepts either letter case. It establishes syntax, not trust in
/// the source that supplied the digest or agreement with artifact bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ArtifactDigest([u8; 32]);

/// The expected text is not exactly 64 ASCII hexadecimal characters.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
#[error("expected a complete SHA-256 digest")]
pub struct InvalidDigest;

impl ArtifactDigest {
    pub(super) fn from_bytes(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }
}

impl TryFrom<&str> for ArtifactDigest {
    type Error = InvalidDigest;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        if value.len() != 64 {
            return Err(InvalidDigest);
        }
        let mut bytes = [0; 32];
        for (output, pair) in bytes.iter_mut().zip(value.as_bytes().chunks_exact(2)) {
            *output = (hex_digit(pair[0])? << 4) | hex_digit(pair[1])?;
        }
        Ok(Self(bytes))
    }
}

impl fmt::Display for ArtifactDigest {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        for byte in self.0 {
            write!(formatter, "{byte:02x}")?;
        }
        Ok(())
    }
}

fn hex_digit(value: u8) -> Result<u8, InvalidDigest> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        b'A'..=b'F' => Ok(value - b'A' + 10),
        _ => Err(InvalidDigest),
    }
}
```

The fallible conversion is an explicit standard trait implementation. `Display` formats a public checksum, so exposing its value is intentional. The error retains no malformed input. `from_bytes` has only the visibility needed by sibling verification code. It accepts a fixed-size value and cannot create a partial digest.

### `apps/cli/xtask/src/checksum/verify.rs`

````rust
//! Verify a borrowed byte source without selecting a filesystem path.

use std::io::{self, Read};

use sha2::{Digest, Sha256};

use super::digest::ArtifactDigest;

/// Observed bytes matched the supplied checksum within the byte budget.
///
/// This record does not authenticate a publisher or protect a later file read.
/// Its public fields are reporting data, not an unforgeable proof capability.
#[derive(Debug, PartialEq, Eq)]
pub struct VerifiedArtifact {
    /// Digest calculated from the consumed bytes.
    pub digest: ArtifactDigest,
    /// Number of artifact bytes consumed on success.
    pub bytes: u64,
}

/// Controlled verification failures that omit arbitrary reader error text.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum VerificationError {
    /// The source could not be read to completion.
    #[error("artifact read failed ({kind:?})")]
    ReadFailed {
        /// Safe category retained from the reader's failure.
        kind: io::ErrorKind,
    },
    /// Reading one byte beyond the budget established that the source is too large.
    #[error("artifact exceeds the byte budget")]
    TooLarge,
    /// Complete content disagreed with the expected digest.
    #[error("artifact checksum does not match")]
    Mismatch,
}

impl From<io::Error> for VerificationError {
    fn from(error: io::Error) -> Self {
        Self::ReadFailed { kind: error.kind() }
    }
}

/// Check a borrowed reader against a parsed digest and maximum byte count.
///
/// The reader remains caller-owned and is not rewound. Rejection may consume
/// input, including one extra byte to detect an oversized source. This bounds
/// consumed data and buffer size, not how long a blocking reader may wait.
///
/// # Errors
/// Returns [`VerificationError::TooLarge`] before hashing data beyond the
/// budget, [`VerificationError::Mismatch`] after a complete unequal digest,
/// or a safe read-error category. Interrupted reads resume without restarting
/// the operation. Arbitrary reader error messages are not retained.
///
/// # Examples
/// ```
/// use std::io::Cursor;
/// use inframeld_cli_xtask::checksum::{ArtifactDigest, verify_reader};
///
/// # fn main() -> Result<(), Box<dyn std::error::Error>> {
/// let expected = ArtifactDigest::try_from(
///     "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
/// )?;
/// let mut source = Cursor::new(b"abc");
/// let verified = verify_reader(&mut source, &expected, 3)?;
/// assert_eq!(verified.bytes, 3);
/// assert_eq!(verified.digest, expected);
/// # Ok(())
/// # }
/// ```
pub fn verify_reader(
    reader: &mut impl Read,
    expected: &ArtifactDigest,
    byte_limit: u64,
) -> Result<VerifiedArtifact, VerificationError> {
    let mut hasher = Sha256::new();
    let mut bytes = 0_u64;
    let mut buffer = [0_u8; 8192];
    loop {
        let remaining = byte_limit - bytes;
        // Probe at most one extra byte without overflowing an unrestricted budget.
        let permitted = usize::try_from(remaining)
            .unwrap_or(usize::MAX)
            .saturating_add(1)
            .min(buffer.len());
        let destination = &mut buffer[..permitted];
        let read = match reader.read(destination) {
            Ok(read) => read,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        };
        if read == 0 {
            break;
        }
        let read_count = u64::try_from(read).map_err(|_| VerificationError::TooLarge)?;
        if read_count > remaining {
            return Err(VerificationError::TooLarge);
        }
        let data = destination
            .get(..read)
            .ok_or(VerificationError::ReadFailed {
                kind: io::ErrorKind::InvalidData,
            })?;
        hasher.update(data);
        bytes += read_count;
    }
    let digest = ArtifactDigest::from_bytes(hasher.finalize().into());
    if &digest != expected {
        return Err(VerificationError::Mismatch);
    }
    Ok(VerifiedArtifact { digest, bytes })
}
````

The operation receives the real capability it needs. There is no `Verifier` object with no reusable state, registry or invented storage protocol. Fixed-buffer streaming avoids reading an entire archive into memory. Saturating probe arithmetic handles even the largest budget. Failure is a `Result`, so optimized builds retain verification. The result never prints itself.

### `apps/cli/xtask/src/checksum/file.rs`

```rust
//! Own the file handle used by a checksum verification operation.

use std::{fs::File, path::Path};

use super::{ArtifactDigest, VerificationError, VerifiedArtifact, verify_reader};

/// Open and verify one file without modifying or executing its contents.
///
/// The handle closes on return. Verification covers this read, not a future
/// reopen, a path replacement or the trustworthiness of the expected digest.
///
/// # Errors
/// Returns a safe read category if opening fails, or a controlled verification
/// failure from [`verify_reader`]. The path and arbitrary I/O text are omitted.
pub fn verify_file(
    path: &Path,
    expected: &ArtifactDigest,
    byte_limit: u64,
) -> Result<VerifiedArtifact, VerificationError> {
    let mut file = File::open(path).map_err(VerificationError::from)?;
    verify_reader(&mut file, expected, byte_limit)
}
```

This adapter owns filesystem selection and handle lifetime. Keeping it separate is useful for teaching the boundary and for callers that already own a reader. A smaller real capability may place this short adapter beside its operation if a separate file would add navigation without value.

## Behavioral qualification

The following is a complete illustrative new test file at `apps/cli/xtask/tests/checksum.rs`. It needs the four files above and their library-root registration. The constants are published test vectors, not credentials. The broken reader supplies a sentinel message to prove that uncontrolled details do not escape.

```rust
use std::io::{self, Cursor, Read};

use inframeld_cli_xtask::checksum::{ArtifactDigest, VerificationError, verify_reader};

const ABC: &str = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
const EMPTY: &str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

#[test]
fn exact_budget_verifies_content() -> Result<(), Box<dyn std::error::Error>> {
    let expected = ArtifactDigest::try_from(ABC)?;
    let mut source = Cursor::new(b"abc");
    let result = verify_reader(&mut source, &expected, 3)?;
    assert_eq!(result.bytes, 3);
    assert_eq!(result.digest, expected);
    Ok(())
}

#[test]
fn excess_content_fails_after_only_one_probe_byte() -> Result<(), Box<dyn std::error::Error>> {
    let expected = ArtifactDigest::try_from(ABC)?;
    let mut source = Cursor::new(b"abcdef");
    assert_eq!(
        verify_reader(&mut source, &expected, 2),
        Err(VerificationError::TooLarge)
    );
    assert_eq!(source.position(), 3);
    Ok(())
}

#[test]
fn unequal_content_is_not_success() -> Result<(), Box<dyn std::error::Error>> {
    let expected = ArtifactDigest::try_from(EMPTY)?;
    assert_eq!(
        verify_reader(&mut Cursor::new(b"abc"), &expected, 3),
        Err(VerificationError::Mismatch)
    );
    Ok(())
}

#[test]
fn zero_budget_accepts_only_empty_input() -> Result<(), Box<dyn std::error::Error>> {
    let expected = ArtifactDigest::try_from(EMPTY)?;
    assert_eq!(verify_reader(&mut Cursor::new(b""), &expected, 0)?.bytes, 0);
    assert_eq!(
        verify_reader(&mut Cursor::new(b"x"), &expected, 0),
        Err(VerificationError::TooLarge)
    );
    Ok(())
}

#[test]
fn maximum_budget_does_not_overflow() -> Result<(), Box<dyn std::error::Error>> {
    let expected = ArtifactDigest::try_from(ABC)?;
    assert_eq!(
        verify_reader(&mut Cursor::new(b"abc"), &expected, u64::MAX)?.bytes,
        3
    );
    Ok(())
}

#[test]
fn digest_parsing_preserves_meaning_and_rejects_malformed_text()
-> Result<(), Box<dyn std::error::Error>> {
    assert_eq!(
        ArtifactDigest::try_from(ABC.to_uppercase().as_str())?.to_string(),
        ABC
    );
    for value in ["", "abc", &"z".repeat(64), &format!("{ABC} ")] {
        assert!(ArtifactDigest::try_from(value).is_err());
    }
    Ok(())
}

struct BrokenReader;

impl Read for BrokenReader {
    fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
        Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "sensitive-reader-sentinel",
        ))
    }
}

#[test]
fn read_failure_retains_category_without_reader_details() -> Result<(), Box<dyn std::error::Error>>
{
    let expected = ArtifactDigest::try_from(ABC)?;
    let error = verify_reader(&mut BrokenReader, &expected, 3)
        .err()
        .ok_or("expected read failure")?;
    assert_eq!(
        error,
        VerificationError::ReadFailed {
            kind: io::ErrorKind::PermissionDenied
        }
    );
    assert!(!format!("{error:?} {error}").contains("sensitive-reader-sentinel"));
    Ok(())
}
```

Further changed-behavior tests should cover actual concerns, such as an interrupted/short reader or concrete file-open failure. Do not test whether modules import the expected names. The tests here establish checksum and bounded-read behavior, not distribution authenticity, full archive qualification, provider behavior or a complete user command.

## Why this is a teaching example rather than copied production code

The [Cargo command/operation split](https://github.com/rust-lang/cargo/blob/master/src/bin/cargo/commands/build.rs), [ripgrep's private components and public facade](https://github.com/BurntSushi/ripgrep/blob/master/crates/printer/src/lib.rs), and [rust-analyzer's function/context guidance](https://rust-analyzer.github.io/book/contributing/style.html#functions-over-objects) inform the boundaries. This implementation is original and narrower than their applications. It includes the necessary imports, failure paths and tests rather than presenting an upstream excerpt as a complete local implementation.

The digest demonstrates encapsulation without a new identity framework. Standard `Read` avoids an unnecessary custom port. The file handle has an obvious owner, and the operation retains controlled rejection in release builds. Adopting this example into application code would still require an authorized change, behavioral TDD, reconciliation with the existing xtask and appropriate package verification.
