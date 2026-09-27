class MigrationLockError(RuntimeError):
    """Stop this migration attempt when another runner holds the lock past the deadline."""
