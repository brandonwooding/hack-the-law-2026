"""Adapter contract: one source -> canonical Document objects.

A jurisdiction has several sources (UK = legislation.gov.uk, the Parliament
APIs, Find Case Law, GOV.UK ...). Each is a SourceAdapter. They share the
Fetcher and emit canonical Documents; everything downstream (load/link/
validate) is source-agnostic.
"""

from __future__ import annotations

import abc

from ..canonical import Document, Jurisdiction
from ..fetch import Fetcher


class SourceAdapter(abc.ABC):
    #: short stable name, e.g. "uk-legislation"
    source: str
    jurisdiction: Jurisdiction

    def __init__(self, fetcher: Fetcher):
        self.fetcher = fetcher

    @abc.abstractmethod
    def collect(self, scope: dict) -> list[Document]:
        """Fetch (via the shared Fetcher, cached) and parse in-scope documents
        into canonical Document objects."""
        raise NotImplementedError
