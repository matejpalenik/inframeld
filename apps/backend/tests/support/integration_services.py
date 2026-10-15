"""Addresses reachable only inside the dedicated integration Compose network."""

POSTGRES_HOST = "postgres"
POSTGRES_PORT = 5432
KRATOS_PUBLIC_URL = "http://kratos:4433"
KRATOS_ADMIN_URL = "http://kratos:4434"
EXPIRING_KRATOS_PUBLIC_URL = "http://kratos-expiring:4433"
HYDRA_PUBLIC_URL = "http://hydra:4444"
HYDRA_ADMIN_URL = "http://hydra:4445"
MAILPIT_URL = "http://mailpit:8025"
MOCK_OIDC_URL = "http://mock-oidc:8080"
RECOVERY_HOOKS_URL = "http://recovery-hooks:8080"
