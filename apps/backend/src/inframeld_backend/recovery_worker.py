"""Start the dedicated recovery process without exposing an HTTP listener."""

from inframeld_backend.bootstrap.recovery_worker import main

if __name__ == "__main__":
    raise SystemExit(main())
