"""Shared test fixtures."""

import pytest
import src.config.llm as llm_config_module


@pytest.fixture(autouse=True)
def _reset_active_llm_config():
    """Isolate the module-level active LLM config between tests.

    ``load_llm_config`` records the active provider for tool-layer helpers
    (e.g. the search-result judge). Without a reset, a config-loading test
    would leak a live provider into later search tests and trigger real LLM
    calls.
    """
    llm_config_module._active_llm_config = None
    yield
    llm_config_module._active_llm_config = None


@pytest.fixture(autouse=True)
def _offline_official_sources(monkeypatch):
    """Search mocks must never trigger an incidental live website request."""
    from src.websearch.sources import _CACHE, OfficialSourceReader, SourceReadError

    _CACHE.clear()

    def unavailable(*args):
        raise SourceReadError('offline_test')

    monkeypatch.setattr(OfficialSourceReader, '_default_transport', staticmethod(unavailable))
    yield
    _CACHE.clear()
