//! Command presentation and generated-client integration for Inframeld.

mod app;
mod arguments;
pub mod client;
mod commands;
pub mod context;
pub mod metadata;

pub use app::run;
pub mod discovery;
