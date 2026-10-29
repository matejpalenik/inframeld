//! Native development tools for packaging and qualifying the CLI.
pub mod archive;

/// Packaging or qualification failed. No success evidence may be emitted.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// A local file, process or installation operation failed.
    #[error(transparent)]
    Io(#[from] std::io::Error),
    /// A metadata or evidence representation could not be encoded or decoded.
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    /// A packaging prerequisite or verification gate rejected the operation.
    #[error("{0}")]
    Invalid(String),
}

/// The existing failure contract shared by private packaging and verification.
pub type Result<T> = std::result::Result<T, Error>;

pub mod package;
mod process;
pub mod verify;
