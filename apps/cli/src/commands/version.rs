//! Present embedded build information through the shared metadata representation.

use crate::metadata::BuildMetadata;
use std::io::{self, Write};

/// Write the same offline version text used by native package qualification.
pub(crate) fn run(output: &mut impl Write) -> io::Result<()> {
    let metadata = BuildMetadata::embedded()
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    write!(output, "{}", metadata.render())
}
