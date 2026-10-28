use crate::metadata::BuildMetadata;
use std::io::{self, Write};

pub(crate) fn version(output: &mut impl Write) -> io::Result<()> {
    let metadata = BuildMetadata::embedded()
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    write!(output, "{}", metadata.render())
}
