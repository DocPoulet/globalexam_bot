"""Paramètres du serveur : les écritures sont interdites par défaut."""
from dataclasses import dataclass
import os


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"true", "1", "yes"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    writes_enabled: bool = False
    min_confirmations: int = 3
    read_limit_day: int = 500
    write_limit_day: int = 200

    @classmethod
    def from_env(cls):
        min_votes = int(os.getenv("COMMUNITY_MIN_CONFIRMATIONS", "3"))
        return cls(
            database_url=os.getenv("DATABASE_URL", ""),
            writes_enabled=env_bool("COMMUNITY_WRITES_ENABLED", False),
            min_confirmations=max(2, min(min_votes, 20)),
            read_limit_day=max(1, min(int(os.getenv("COMMUNITY_READ_LIMIT_DAY", "500")), 100000)),
            write_limit_day=max(1, min(int(os.getenv("COMMUNITY_WRITE_LIMIT_DAY", "200")), 10000)),
        )
