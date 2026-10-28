"""Private integration endpoints and shared fixture paths."""

from pathlib import Path

TLS_TRUST_DIRECTORY = Path("/run/inframeld-test-tls/trust")
TLS_IDENTITY_DIRECTORY = Path("/run/inframeld-test-tls/identity")
TLS_CA_FILE = TLS_TRUST_DIRECTORY / "ca.pem"
TLS_EXPIRY_FILE = TLS_TRUST_DIRECTORY / "server-not-after.txt"

POSTGRES_HOST = "postgres"
POSTGRES_PORT = 5432
KRATOS_PUBLIC_URL = "http://kratos:4433"
KRATOS_ADMIN_URL = "http://kratos:4434"
EXPIRING_KRATOS_PUBLIC_URL = "http://kratos-expiring:4433"
HYDRA_PUBLIC_URL = "http://hydra:4444"
HYDRA_ADMIN_URL = "http://hydra:4445"
LIFETIME_HYDRA_PUBLIC_URL = "http://hydra-lifetimes:4444"
LIFETIME_HYDRA_ADMIN_URL = "http://hydra-lifetimes:4445"
MAILPIT_URL = "http://mailpit:8025"
MOCK_OIDC_URL = "http://mock-oidc:8080"
RECOVERY_HOOKS_URL = "http://recovery-hooks:8080"
PASSWORD_BREACHES_URL = "https://password-breaches:8443"
