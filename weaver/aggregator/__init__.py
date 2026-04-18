"""Aggregator: fetch authoritative sources to disk. Indexing happens later."""
from weaver.aggregator.cache import CacheLayout, iter_cached_items
from weaver.aggregator.fetcher import FetchResult, fetch_source
from weaver.aggregator.sources import Source, load_sources
from weaver.aggregator.state import SourceState, load_state, save_state

__all__ = [
    "CacheLayout", "FetchResult", "Source", "SourceState",
    "fetch_source", "iter_cached_items", "load_sources", "load_state", "save_state",
]
