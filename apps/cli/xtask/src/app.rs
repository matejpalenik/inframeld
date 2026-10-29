//! Dispatch a private tooling invocation and emit its existing evidence output.

use inframeld_cli_xtask::{Result, archive, package, verify};

use crate::arguments::{Arguments, Task};

/// Run the selected operation without changing its packaging or qualification policy.
pub(crate) fn run(arguments: Arguments) -> Result<()> {
    match arguments.command {
        Task::Package {
            target,
            reproducible,
        } => package::run(target, reproducible),
        Task::Normalize {
            archive: path,
            epoch,
        } => archive::normalize(&path, epoch),
        Task::Verify { archive, target } => {
            println!(
                "{}",
                serde_json::to_string_pretty(&verify::artifact(&archive, &target)?)?
            );
            Ok(())
        }
    }
}
