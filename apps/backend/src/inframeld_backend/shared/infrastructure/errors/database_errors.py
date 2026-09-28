class DatabaseStartupError(RuntimeError):
    """Stop startup when PostgreSQL cannot be reached or its schema is incompatible."""


class DatabaseSchemaCompatibilityError(DatabaseStartupError):
    """Require operator migration before serving against an unsupported schema."""
