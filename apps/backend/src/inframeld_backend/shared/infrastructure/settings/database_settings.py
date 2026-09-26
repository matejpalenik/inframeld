"""Validate PostgreSQL connection, pool, and migration timeout configuration."""

from typing import Annotated

from pydantic import BaseModel, Field, SecretStr

Port = Annotated[int, Field(ge=1, le=65_535)]
PoolSize = Annotated[int, Field(ge=1, le=100)]
PoolOverflow = Annotated[int, Field(ge=0, le=100)]
ConnectTimeoutSeconds = Annotated[int, Field(ge=1, le=60)]
StartupTimeoutSeconds = Annotated[float, Field(gt=0, le=60)]
PoolTimeoutSeconds = Annotated[float, Field(gt=0, le=300)]
MigrationLockTimeoutSeconds = Annotated[float, Field(gt=0, le=300)]


class DatabaseSettings(BaseModel):
    """Bound PostgreSQL connection resources and keep the password secret in representations."""

    host: str = Field(default="localhost", min_length=1)
    port: Port = 5432
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: SecretStr

    pool_size: PoolSize = 10
    max_overflow: PoolOverflow = 20

    connect_timeout_seconds: ConnectTimeoutSeconds = 5
    startup_timeout_seconds: StartupTimeoutSeconds = 10.0
    pool_timeout_seconds: PoolTimeoutSeconds = 30.0
    migration_lock_timeout_seconds: MigrationLockTimeoutSeconds = 5.0
