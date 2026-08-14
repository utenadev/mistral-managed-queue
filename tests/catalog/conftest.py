"""Catalog tests require the optional [catalog] extras (httpx + PyYAML).

Skip collection entirely when they are missing so `pytest tests/` still works
with a base install of mistral-managed-queue.
"""

import pytest


def pytest_collection_modifyitems(session, config, items):
    try:
        import httpx  # noqa: F401
        import yaml  # noqa: F401
        from mmq.catalog import fetch_catalog  # noqa: F401
    except ImportError:
        skip = pytest.mark.skip(
            reason="requires mmq[catalog] extras (httpx + PyYAML)"
        )
        for item in items:
            item.add_marker(skip)
