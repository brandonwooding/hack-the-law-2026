"""Jurisdiction-specific source adapters — the only per-source code."""

from .base import SourceAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {}


def register(name: str):
    def _wrap(cls: type[SourceAdapter]) -> type[SourceAdapter]:
        ADAPTERS[name] = cls
        return cls

    return _wrap
