"""Shared test fixtures. FakeDriver lets us unit-test retrieval/regime code
without a live Neo4j — it returns canned rows keyed by a substring of the
Cypher, and records every (cypher, params) call for assertions."""
from __future__ import annotations

from contextlib import contextmanager


class _Row:
    def __init__(self, d: dict):
        self._d = d

    def data(self) -> dict:
        return self._d


class _Session:
    def __init__(self, driver: "FakeDriver"):
        self._driver = driver

    def run(self, cypher: str, **params):
        self._driver.calls.append((cypher, params))
        for substring, rows in self._driver.rows_by_substring.items():
            if substring in cypher:
                return [_Row(r) for r in rows]
        return []


class FakeDriver:
    def __init__(self, rows_by_substring: dict[str, list[dict]] | None = None):
        self.rows_by_substring = rows_by_substring or {}
        self.calls: list[tuple[str, dict]] = []

    @contextmanager
    def session(self, database=None):
        yield _Session(self)

    def close(self):
        pass
