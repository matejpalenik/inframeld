import sys

from inframeld_backend.bootstrap.oauth_client_provisioning import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
