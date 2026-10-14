"""Contrôles Railway hors ligne : aucun appel SQL/cloud réel."""
from pathlib import Path
from unittest.mock import Mock

from server.store import PostgresStore


class FakeConnection:
    def __init__(self, value=True):
        self.value = value
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "to_regclass" in sql:
            return Mock(fetchone=lambda: {"ready": self.value})
        return Mock()


def test_postgres_ready_requires_tables(monkeypatch):
    store = PostgresStore("postgresql://dummy")
    conn = FakeConnection(True)
    monkeypatch.setattr(store, "_connect", lambda: conn)
    assert store.ready() is True
    sql = conn.calls[0][0]
    assert "community_clients" in sql
    assert "community_contributions" in sql
    assert "community_api_usage" in sql
    conn.value = False
    assert store.ready() is False


def test_schema_init_uses_advisory_lock(monkeypatch):
    store = PostgresStore("postgresql://dummy")
    conn = FakeConnection()
    monkeypatch.setattr(store, "_connect", lambda: conn)
    store.init_db()
    assert "pg_advisory_xact_lock" in conn.calls[0][0]
    assert any("CREATE TABLE" in sql for sql, _ in conn.calls)


def test_dockerfile_supports_railway_port_without_cloud_secrets():
    docker = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert "${PORT:-8000}" in docker
    assert "--host 0.0.0.0" in docker
    assert "COPY src " in docker
    assert "COPY server " in docker
    assert "DATABASE_URL=" not in docker
    assert "COMMUNITY_WRITES_ENABLED=true" not in docker


def test_railway_example_writes_disabled():
    content = (Path(__file__).resolve().parents[1] / "railway.env.example").read_text()
    assert "COMMUNITY_WRITES_ENABLED=false" in content
    assert "Postgres.DATABASE_URL" in content
    assert "REPLACE_WITH" not in content
