//! Native development tools for packaging and qualifying the CLI.
pub mod archive;

/// Packaging or qualification failed. No success evidence may be emitted.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error("{0}")]
    Invalid(String),
}

pub type Result<T> = std::result::Result<T, Error>;

pub mod package;
mod process;
pub mod verify;
