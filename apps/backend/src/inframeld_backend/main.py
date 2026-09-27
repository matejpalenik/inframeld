"""Expose the executable ASGI application; tools should import the bootstrap factory directly."""

from inframeld_backend.bootstrap.application_factory import create_app

app = create_app()
