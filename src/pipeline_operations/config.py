"""Environment boundary for operational state stored in PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class OperationsSettings:
    postgres_host: str = "postgresql"
    postgres_port: int = 5432
    database: str = "financial_metadata"
    user: str = "metadata_user"
    password: str = "metadata_password"
    schema: str = "pipeline_operations"

    @classmethod
    def from_env(cls) -> "OperationsSettings":
        port = int(os.getenv("METADATA_POSTGRES_INTERNAL_PORT", "5432"))
        if not 1 <= port <= 65535:
            raise ValueError("METADATA_POSTGRES_INTERNAL_PORT must be between 1 and 65535")
        return cls(
            postgres_host=os.getenv("METADATA_POSTGRES_HOST", cls.postgres_host),
            postgres_port=port,
            database=os.getenv("METADATA_POSTGRES_DB", cls.database),
            user=os.getenv("METADATA_POSTGRES_USER", cls.user),
            password=os.getenv("METADATA_POSTGRES_PASSWORD", cls.password),
            schema=os.getenv("PIPELINE_OPERATIONS_SCHEMA", cls.schema),
        )

    @property
    def connection_kwargs(self) -> dict:
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "connect_timeout": 10,
        }
