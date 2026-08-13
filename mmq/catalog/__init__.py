"""Catalog module for fetching and exporting ORR-compatible provider/model YAML.

This module provides the core functionality for fetching model catalog information
from various providers (OpenRouter, NVIDIA NIM, Mistral) and exporting it
in the ORR Catalog YAML format.

See docs/DESIGN_model-catalog.md and docs/DESIGN_model-catalog_detail.md
for the full design specification.
"""

from mmq.catalog.types import (
    SCHEMA_VERSION,
    PROVIDER_OPENROUTER,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_MISTRAL,
    PriceStatus,
)
from mmq.catalog.fetch import fetch_catalog, FetchResult
from mmq.catalog.write import write_catalog_yaml, default_catalog_path
from mmq.catalog.validate import validate_catalog

__all__ = [
    # Constants
    "SCHEMA_VERSION",
    "PROVIDER_OPENROUTER",
    "PROVIDER_NVIDIA_NIM",
    "PROVIDER_MISTRAL",
    # Types
    "PriceStatus",
    "FetchResult",
    # Functions
    "fetch_catalog",
    "write_catalog_yaml",
    "default_catalog_path",
    "validate_catalog",
]
