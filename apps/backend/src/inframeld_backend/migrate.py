"""Run operator-controlled migrations with safe failure reporting."""

from inframeld_backend.shared.infrastructure.error_reporting import report_unexpected_error
from inframeld_backend.shared.infrastructure.logging import configure_logging
from inframeld_backend.shared.infrastructure.migrations import run_migrations
from inframeld_backend.shared.infrastructure.settings import get_settings


def main() -> int:
    """Apply migrations, returning a failing exit status without raw exception text."""
    settings = None

    try:
        settings = get_settings()
        run_migrations(settings.database)
    except Exception as error:
        # Alembic's env.py installs its own logging configuration. Restore our
        # sanitized formatter before reporting the failure.
        configure_logging(
            level="ERROR",
            log_format=settings.log_format if settings is not None else "json",
        )
        report_unexpected_error(error, event="migration_failed")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
