"""Catalog tests require the optional [catalog] extras (httpx + PyYAML).

Skip collection when they are missing so `pytest tests/` still works
with a base install of mistral-managed-queue.
"""

try:
    import httpx  # noqa: F401
    import yaml  # noqa: F401
    from mmq.catalog import fetch_catalog  # noqa: F401
except ImportError:
    # Without catalog deps, ignore every test file in this directory.
    # collect_ignore_glob is evaluated by pytest before full collection.
    collect_ignore_glob = ["*.py"]
