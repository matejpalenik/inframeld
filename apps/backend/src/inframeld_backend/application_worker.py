"""Start the ordinary database-backed application worker without an HTTP listener."""

from inframeld_backend.bootstrap.application_worker import main

if __name__ == "__main__":
    raise SystemExit(main())
