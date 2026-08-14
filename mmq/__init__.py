"""mistral-managed-queue - Mistral API queue with rate limiting.

This package provides:
- MCP server for Mistral API with priority queue and rate limiting (lazy init)
- Catalog fetching via mmq.catalog (optional: pip install mistral-managed-queue[catalog])

New code should import from specific submodules:
    from mmq.catalog import fetch_catalog, write_catalog_yaml, ...
    from mmq.cli import main as cli_main
"""

__version__ = "0.2.0"

# Catalog module is available via mmq.catalog (requires httpx+PyYAML).
# Install with: pip install mistral-managed-queue[catalog]

# Re-export CLI main for console script
from mmq.cli import main as cli_main

__all__ = [
    # Only core exports; catalog is available via mmq.catalog (extras).
    "cli_main",
    "__version__",
]
