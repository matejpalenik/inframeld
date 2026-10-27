"""Run protected maintenance from the deployment host or container exec."""

from inframeld_backend.bootstrap.maintenance import main

if __name__ == "__main__":
    raise SystemExit(main())
