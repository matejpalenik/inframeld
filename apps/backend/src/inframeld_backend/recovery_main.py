"""Serve trusted Kratos notifications on the deployment's private network."""

from inframeld_backend.bootstrap.recovery_application_factory import create_recovery_app

app = create_recovery_app()
