"""Replaceable unit-of-work boundary; the mock is process-local and thread-safe."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, ContextManager, Iterator, Protocol

Record = dict[str, Any]


class UnitOfWork(Protocol):
    def settings(self) -> Record: ...
    def save_settings(self, value: Record) -> None: ...
    def parties(self) -> list[Record]: ...
    def party(self, party_id: str) -> Record | None: ...
    def save_party(self, party: Record) -> None: ...
    def next_order(self) -> int: ...
    def events(self, party_id: str) -> list[Record]: ...
    def append_event(self, party_id: str, event: Record) -> None: ...
    def receipt(self, key: str) -> Record | None: ...
    def save_receipt(self, key: str, value: Record) -> None: ...
    def session(self, key: str) -> Record | None: ...
    def save_session(self, key: str, value: Record) -> None: ...
    def delete_session(self, key: str) -> None: ...
    def increment_rate(self, key: str, window: int) -> int: ...
    def prune_sessions(self, now: Any) -> None: ...


class Repository(Protocol):
    def atomic(self) -> ContextManager[UnitOfWork]: ...


@dataclass
class MemoryState:
    settings: Record
    parties: dict[str, Record] = field(default_factory=dict)
    events: dict[str, list[Record]] = field(default_factory=dict)
    receipts: dict[str, Record] = field(default_factory=dict)
    sessions: dict[str, Record] = field(default_factory=dict)
    rate: dict[str, Record] = field(default_factory=dict)
    order: int = 0


class MemoryUnitOfWork:
    def __init__(self, state: MemoryState):
        self._state = state

    def settings(self):
        return deepcopy(self._state.settings)

    def save_settings(self, value):
        self._state.settings = deepcopy(value)

    def parties(self):
        return deepcopy(list(self._state.parties.values()))

    def party(self, party_id):
        return deepcopy(self._state.parties.get(party_id))

    def save_party(self, party):
        self._state.parties[party["id"]] = deepcopy(party)

    def next_order(self):
        self._state.order += 1
        return self._state.order

    def events(self, party_id):
        return deepcopy(self._state.events.get(party_id, []))

    def append_event(self, party_id, event):
        self._state.events.setdefault(party_id, []).append(deepcopy(event))

    def receipt(self, key):
        return deepcopy(self._state.receipts.get(key))

    def save_receipt(self, key, value):
        self._state.receipts[key] = deepcopy(value)

    def session(self, key):
        return deepcopy(self._state.sessions.get(key))

    def save_session(self, key, value):
        self._state.sessions[key] = deepcopy(value)

    def delete_session(self, key):
        self._state.sessions.pop(key, None)

    def prune_sessions(self, now):
        self._state.sessions = {
            k: v for k, v in self._state.sessions.items() if v["expires_at"] > now
        }

    def increment_rate(self, key, window):
        self._state.rate = {k: v for k, v in self._state.rate.items() if v["window"] >= window}
        item = self._state.rate.setdefault(key, {"window": window, "count": 0})
        item["count"] += 1
        return item["count"]


class InMemoryRepository:
    """Copy-on-write transactions roll back on exceptions; an RLock orders all writes.

    Deliberately optimized for understandable mocks, not large datasets. Never run
    multiple API workers with this adapter: each worker would have its own state.
    """

    def __init__(self, name="TableTurn Restaurant", timezone="America/Los_Angeles"):
        self._state = MemoryState(
            settings={
                "name": name,
                "timezone": timezone,
                "is_open": True,
                "max_party_size": 30,
                "grace_seconds": 300,
                "version": 1,
            }
        )
        self._lock = RLock()

    @contextmanager
    def atomic(self) -> Iterator[MemoryUnitOfWork]:
        with self._lock:
            draft = deepcopy(self._state)
            yield MemoryUnitOfWork(draft)
            self._state = draft
