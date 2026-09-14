"""SQLAlchemy Core adapter. Domain services depend only on Repository/UnitOfWork.

One restaurant-wide lock serializes transactions across connections, preserving
queue order, optimistic versions and idempotency. No vendor-specific SQL is used.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import secrets

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def encode(value):
    if isinstance(value, datetime):
        return {"__tableturn_datetime__": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [encode(v) for v in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if set(value) == {"__tableturn_datetime__"}:
            return datetime.fromisoformat(value["__tableturn_datetime__"])
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


metadata = MetaData()
control = Table(
    "restaurant",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("lock_version", Integer, nullable=False),
    Column("queue_order", Integer, nullable=False),
    Column("settings", JSON, nullable=False),
    Column("link_secret", Text, nullable=False),
)
parties = Table(
    "parties",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("size", Integer, nullable=False),
    Column("state", String(20), nullable=False, index=True),
    Column("order", Integer, nullable=False, unique=True),
    Column("version", Integer, nullable=False),
    Column("token_digest", String(64), nullable=False, unique=True),
    *(
        Column(key, UTCDateTime(), nullable=key not in ("joined_at", "updated_at"))
        for key in (
            "joined_at",
            "updated_at",
            "ready_at",
            "deadline",
            "seated_at",
            "no_show_at",
            "cancelled_at",
        )
    ),
)
events = Table(
    "party_events",
    metadata,
    Column("party_id", String(36), ForeignKey("parties.id"), primary_key=True),
    Column("sequence", Integer, primary_key=True),
    Column("data", JSON, nullable=False),
)
receipts = Table(
    "receipts",
    metadata,
    Column("id", String(240), primary_key=True),
    Column("data", JSON, nullable=False),
)
sessions = Table(
    "sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("data", JSON, nullable=False),
    Column("expires_at", UTCDateTime(), nullable=False, index=True),
)
rates = Table(
    "rate_limits",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("window", Integer, nullable=False, index=True),
    Column("count", Integer, nullable=False),
)


class SQLAlchemyUnitOfWork:
    def __init__(self, connection):
        self.connection = connection

    def _get(self, table, key):
        row = self.connection.execute(select(table).where(table.c.id == key)).mappings().first()
        return dict(row) if row else None

    def _save(self, table, key, values):
        if self._get(table, key) is None:
            self.connection.execute(insert(table).values(id=key, **values))
        else:
            self.connection.execute(update(table).where(table.c.id == key).values(**values))

    def settings(self):
        return self._get(control, 1)["settings"]

    def save_settings(self, value):
        self.connection.execute(update(control).where(control.c.id == 1).values(settings=value))

    def parties(self):
        return [dict(row) for row in self.connection.execute(select(parties)).mappings()]

    def party(self, party_id):
        return self._get(parties, party_id)

    def save_party(self, party):
        self._save(parties, party["id"], {k: v for k, v in party.items() if k != "id"})

    def next_order(self):
        value = self._get(control, 1)["queue_order"] + 1
        self.connection.execute(update(control).where(control.c.id == 1).values(queue_order=value))
        return value

    def events(self, party_id):
        rows = self.connection.execute(
            select(events.c.data).where(events.c.party_id == party_id).order_by(events.c.sequence)
        )
        return [decode(row[0]) for row in rows]

    def append_event(self, party_id, event):
        self.connection.execute(
            insert(events).values(
                party_id=party_id, sequence=len(self.events(party_id)) + 1, data=encode(event)
            )
        )

    def receipt(self, key):
        row = self._get(receipts, key)
        return decode(row["data"]) if row else None

    def save_receipt(self, key, value):
        self._save(receipts, key, {"data": encode(value)})

    def session(self, key):
        row = self._get(sessions, key)
        return decode(row["data"]) if row else None

    def save_session(self, key, value):
        self._save(sessions, key, {"data": encode(value), "expires_at": value["expires_at"]})

    def delete_session(self, key):
        self.connection.execute(delete(sessions).where(sessions.c.id == key))

    def prune_sessions(self, now):
        self.connection.execute(delete(sessions).where(sessions.c.expires_at <= now))

    def increment_rate(self, key, window):
        self.connection.execute(delete(rates).where(rates.c.window < window))
        row = self._get(rates, key)
        count = row["count"] + 1 if row else 1
        self._save(rates, key, {"window": window, "count": count})
        return count


class SQLAlchemyRepository:
    storage = "sqlalchemy"

    def __init__(self, url, name="TableTurn Restaurant", timezone="America/Los_Angeles"):
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite" and (
            not parsed.database
            or parsed.database == ":memory:"
            or parsed.query.get("mode") == "memory"
        ):
            raise ValueError("Use a persistent SQLite file for SQLAlchemyRepository")
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            **(
                {"connect_args": {"check_same_thread": False, "timeout": 30}}
                if str(url).startswith("sqlite")
                else {}
            ),
        )
        metadata.create_all(self.engine)
        # Bootstrap before serving traffic. The PK resolves simultaneous seed inserts.
        try:
            with self.engine.begin() as connection:
                if (
                    connection.execute(select(control.c.id).where(control.c.id == 1)).first()
                    is None
                ):
                    connection.execute(
                        insert(control).values(
                            id=1,
                            lock_version=0,
                            queue_order=0,
                            link_secret=secrets.token_hex(32),
                            settings={
                                "name": name,
                                "timezone": timezone,
                                "is_open": True,
                                "max_party_size": 30,
                                "grace_seconds": 300,
                                "version": 1,
                            },
                        )
                    )
        except IntegrityError:
            with self.engine.connect() as connection:
                if (
                    connection.execute(select(control.c.id).where(control.c.id == 1)).first()
                    is None
                ):
                    raise

    @contextmanager
    def atomic(self):
        with self.engine.begin() as connection:
            # UPDATE acquires a write lock even on SQLite, unlike SELECT FOR UPDATE.
            # Take it before reading any state to avoid read-to-write upgrade races.
            connection.execute(
                update(control)
                .where(control.c.id == 1)
                .values(lock_version=control.c.lock_version + 1)
            )
            yield SQLAlchemyUnitOfWork(connection)

    def link_secret(self):
        with self.atomic() as tx:
            return tx._get(control, 1)["link_secret"].encode()

    def close(self):
        self.engine.dispose()


if __name__ == "__main__":
    import os
    from pathlib import Path

    repository = SQLAlchemyRepository(
        os.getenv(
            "DATABASE_URL", "sqlite:///" + str(Path(__file__).resolve().parents[1] / "tableturn.db")
        ),
        os.getenv("RESTAURANT_NAME", "TableTurn Restaurant"),
        os.getenv("RESTAURANT_TIMEZONE", "America/Los_Angeles"),
    )
    repository.close()
    print("Database schema initialized.")
