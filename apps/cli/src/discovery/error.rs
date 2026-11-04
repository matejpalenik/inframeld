//! Retain declared public problems without upstream bodies or credential-bearing errors.

use std::{error::Error, fmt};

use inframeld_sdk::client::{ApiOpError, HttpError};
use inframeld_sdk::types::{ProblemDetails, ValidationIssue, ValidationIssuePathItemUnion};
use serde::{Serialize, Serializer};

/// A bounded declared backend problem admitted for reporting, not installation trust.
///
/// Only the reporting allowlist is serialized. Debug output omits all response text.
/// Construction checks constraints not enforced by the generated decoder, plus
/// status and request-ID correlation with the same HTTP response.
#[derive(Clone)]
pub struct DiscoveryProblem(ProblemDetails);

impl DiscoveryProblem {
    fn admit(
        problem: ProblemDetails,
        status: u16,
        headers: &reqwest::header::HeaderMap,
    ) -> Result<Self, DiscoveryError> {
        let mut request_ids = headers.get_all("x-request-id").iter();
        let request_id = request_ids
            .next()
            .and_then(|value| value.to_str().ok())
            .and_then(|value| uuid::Uuid::parse_str(value).ok());
        if request_ids.next().is_some()
            || problem.status != i64::from(status)
            || request_id != Some(problem.request_id)
            || !bounded_text(problem.r#type.as_str(), 2048)
            || !bounded_text(&problem.title, 128)
            || !bounded_text(&problem.detail, 512)
            || !problem_code(&problem.code)
            || problem
                .operation_id
                .as_ref()
                .and_then(Option::as_ref)
                .is_some_and(String::is_empty)
            || problem
                .errors
                .as_ref()
                .and_then(Option::as_ref)
                .is_some_and(|issues| {
                    issues.len() > 20
                        || issues.iter().any(|issue| {
                            !problem_code(&issue.code)
                                || !bounded_text(&issue.message, 256)
                                || issue.path.len() > 8
                                || issue.path.iter().any(|part| match part {
                                    ValidationIssuePathItemUnion::String(value) => {
                                        !bounded_text(value, 64)
                                    }
                                    ValidationIssuePathItemUnion::Integer(value) => *value < 0,
                                })
                        })
                })
        {
            return Err(DiscoveryError::InvalidMetadata);
        }
        Ok(Self(problem))
    }
}

fn bounded_text(value: &str, maximum: usize) -> bool {
    !value.is_empty() && value.chars().count() <= maximum
}

fn problem_code(value: &str) -> bool {
    value.len() <= 64
        && value.as_bytes().first().is_some_and(u8::is_ascii_lowercase)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}

/// Explicit borrowed views keep future SDK fields outside the CLI's reporting contract.
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
#[allow(
    clippy::option_option,
    reason = "The published SDK fields distinguish absence, null and a value."
)]
struct ProblemReport<'a> {
    #[serde(rename = "type")]
    type_uri: &'a url::Url,
    title: &'a str,
    status: i64,
    detail: &'a str,
    code: &'a str,
    request_id: uuid::Uuid,
    #[serde(skip_serializing_if = "Option::is_none")]
    errors: Option<Option<Vec<IssueReport<'a>>>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    operation_id: &'a Option<Option<String>>,
}

#[derive(Serialize)]
struct IssueReport<'a> {
    location: &'a inframeld_sdk::types::ValidationIssueLocation,
    path: &'a [ValidationIssuePathItemUnion],
    code: &'a str,
    message: &'a str,
}

impl Serialize for DiscoveryProblem {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let problem = &self.0;
        ProblemReport {
            type_uri: &problem.r#type,
            title: &problem.title,
            status: problem.status,
            detail: &problem.detail,
            code: &problem.code,
            request_id: problem.request_id,
            errors: problem.errors.as_ref().map(|issues| {
                issues.as_ref().map(|issues| {
                    issues
                        .iter()
                        .map(|issue| IssueReport {
                            location: &issue.location,
                            path: &issue.path,
                            code: &issue.code,
                            message: &issue.message,
                        })
                        .collect()
                })
            }),
            operation_id: &problem.operation_id,
        }
        .serialize(serializer)
    }
}

impl fmt::Debug for DiscoveryProblem {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("DiscoveryProblem([REDACTED])")
    }
}

impl fmt::Display for DiscoveryProblem {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let problem = &self.0;
        write!(
            formatter,
            "{}: {} (code {}, status {}, request {})",
            problem.title.escape_debug(),
            problem.detail.escape_debug(),
            problem.code,
            problem.status,
            problem.request_id
        )
    }
}

// Preserve discovery's existing equality API without new copies of SDK issue/path types.
impl PartialEq for DiscoveryProblem {
    fn eq(&self, other: &Self) -> bool {
        let (left, right) = (&self.0, &other.0);
        left.r#type == right.r#type
            && left.title == right.title
            && left.status == right.status
            && left.detail == right.detail
            && left.code == right.code
            && left.request_id == right.request_id
            && left.operation_id == right.operation_id
            && match (&left.errors, &right.errors) {
                (None, None) | (Some(None), Some(None)) => true,
                (Some(Some(left)), Some(Some(right))) => {
                    left.len() == right.len()
                        && left
                            .iter()
                            .zip(right)
                            .all(|(left, right)| same_issue(left, right))
                }
                _ => false,
            }
    }
}

impl Eq for DiscoveryProblem {}

fn same_issue(left: &ValidationIssue, right: &ValidationIssue) -> bool {
    left.location == right.location
        && left.code == right.code
        && left.message == right.message
        && left.path.len() == right.path.len()
        && left
            .path
            .iter()
            .zip(&right.path)
            .all(|(left, right)| match (left, right) {
                (
                    ValidationIssuePathItemUnion::String(left),
                    ValidationIssuePathItemUnion::String(right),
                ) => left == right,
                (
                    ValidationIssuePathItemUnion::Integer(left),
                    ValidationIssuePathItemUnion::Integer(right),
                ) => left == right,
                _ => false,
            })
}

/// A discovery failure safe for human or machine presentation.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum DiscoveryError {
    /// The supplied identifier is not an allowed public URL.
    #[error("provide a canonical HTTPS API URL without credentials, query or fragment")]
    InvalidUrl,
    /// Public identity disagrees with the requested profile.
    #[error("discovery identity does not match the requested installation")]
    IdentityMismatch,
    /// Metadata is malformed or lacks required protocol configuration.
    #[error("invalid discovery metadata")]
    InvalidMetadata,
    /// The server advertises an unsupported first-party profile.
    #[error("unsupported discovery profile or transport configuration")]
    UnsupportedProfile,
    /// The server did not return successful metadata.
    #[error("discovery metadata is unavailable")]
    Unavailable,
    /// A declared backend problem passed reporting bounds and response correlation.
    #[error("{0}")]
    BackendProblem(Box<DiscoveryProblem>),
    /// The TLS certificate could not be verified.
    #[error("discovery TLS verification failed")]
    Tls,
    /// Discovery never follows redirects.
    #[error("discovery redirects are not permitted")]
    Redirect,
    /// A response exceeded the fixed discovery budget.
    #[error("discovery response exceeds 64 KiB")]
    ResponseTooLarge,
    /// A per-request or overall deadline elapsed.
    #[error("discovery timed out")]
    Timeout,
    /// A connection failed without a usable response.
    #[error("discovery connection failed")]
    Transport,
}

/// Walk structured causes without preserving or searching arbitrary error text.
pub(super) fn transport_error(error: &(dyn Error + 'static)) -> DiscoveryError {
    let mut source: Option<&(dyn Error + 'static)> = Some(error);
    while let Some(item) = source {
        if item
            .downcast_ref::<reqwest::Error>()
            .is_some_and(reqwest::Error::is_timeout)
        {
            return DiscoveryError::Timeout;
        }
        if let Some(inner) = item
            .downcast_ref::<std::io::Error>()
            .and_then(std::io::Error::get_ref)
        {
            let classified = transport_error(inner);
            if classified != DiscoveryError::Transport {
                return classified;
            }
        }
        if matches!(
            item.downcast_ref::<rustls::Error>(),
            Some(rustls::Error::InvalidCertificate(_))
        ) {
            return DiscoveryError::Tls;
        }
        source = item.source();
    }
    DiscoveryError::Transport
}

/// Classify SDK input, status and transport failures without retaining their messages.
pub(super) fn sdk_error<E: fmt::Debug>(
    error: ApiOpError<E>,
    declared_problem: impl FnOnce(E) -> Option<ProblemDetails>,
) -> DiscoveryError {
    match error {
        ApiOpError::Transport(HttpError::Serialization(_)) => DiscoveryError::InvalidUrl,
        ApiOpError::Transport(HttpError::ResponseTooLarge { .. }) => {
            DiscoveryError::ResponseTooLarge
        }
        ApiOpError::Transport(HttpError::Network(error)) => transport_error(&error),
        ApiOpError::Transport(HttpError::Timeout) => DiscoveryError::Timeout,
        ApiOpError::Transport(HttpError::Middleware(error)) if error.is_timeout() => {
            DiscoveryError::Timeout
        }
        ApiOpError::Transport(error) => transport_error(&error),
        ApiOpError::Api(error) if (300..400).contains(&error.status) => DiscoveryError::Redirect,
        ApiOpError::Api(error) if error.status == 200 => DiscoveryError::InvalidMetadata,
        ApiOpError::Api(error) if matches!(error.status, 404 | 422 | 503) => {
            match error.typed.and_then(declared_problem) {
                Some(problem) => {
                    match DiscoveryProblem::admit(problem, error.status, &error.headers) {
                        Ok(problem) => DiscoveryError::BackendProblem(Box::new(problem)),
                        Err(error) => error,
                    }
                }
                None => DiscoveryError::Unavailable,
            }
        }
        ApiOpError::Api(_) => DiscoveryError::Unavailable,
    }
}

#[cfg(test)]
mod tests {
    use super::{ApiOpError, DiscoveryError, HttpError, sdk_error};

    #[test]
    fn serialization_rejection_is_a_safe_input_error() {
        let sentinel = "private-discovery-credential";
        let error = sdk_error::<()>(
            ApiOpError::Transport(HttpError::Serialization(sentinel.to_owned())),
            |()| None,
        );
        assert_eq!(error, DiscoveryError::InvalidUrl);
        assert!(!error.to_string().contains(sentinel));
        assert!(!format!("{error:?}").contains(sentinel));
        assert!(std::error::Error::source(&error).is_none());
    }
}
