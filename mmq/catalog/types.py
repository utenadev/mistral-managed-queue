"""Type definitions for ORR Catalog.

This module defines the data structures and constants used throughout
the catalog fetching and exporting pipeline.

See docs/DESIGN_model-catalog_detail.md for the complete schema specification.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict

# ---------------------------------------------------------------------------
# Constants (API Name Freeze - do not change)
# ---------------------------------------------------------------------------

SCHEMA_VERSION: int = 1

# Provider IDs (stable strings - do not change)
PROVIDER_OPENROUTER: str = "openrouter"
PROVIDER_NVIDIA_NIM: str = "nvidia_nim"
PROVIDER_MISTRAL: str = "mistral"

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Price status enumeration
PriceStatus = Literal["known", "free", "dynamic", "unknown"]

# Auth type enumeration (P1: only bearer_env)
AuthType = Literal["bearer_env"]

# ---------------------------------------------------------------------------
# Data structures (TypedDict for type safety)
# ---------------------------------------------------------------------------


class AuthDict(TypedDict):
    """Authentication configuration for a provider."""
    
    type: AuthType
    env: str  # Environment variable name (e.g., "OPENROUTER_API_KEY")


class CapabilitiesDict(TypedDict):
    """Provider capabilities flags."""
    
    catalog: bool
    chat: bool


class SourceDict(TypedDict):
    """Metadata about the catalog fetch source."""
    
    list_endpoint: str
    fetched_at: str  # RFC3339 UTC timestamp
    warnings: List[str]
    error: Optional[str]  # Non-null if provider fetch failed entirely


class ModelDict(TypedDict, total=False):
    """A single model entry in the catalog.
    
    All fields except 'id' and 'price_status' are optional.
    """
    
    # Required
    id: str
    price_status: PriceStatus
    
    # Optional (can be None)
    name: Optional[str]
    context_length: Optional[int]
    modality: Optional[str]
    prompt_price: Optional[float]
    completion_price: Optional[float]
    canonical_slug: Optional[str]
    coding_index: Optional[float]
    intelligence_index: Optional[float]
    expiration_date: Optional[str]  # YYYY-MM-DD or null
    supported_params: Optional[List[str]]
    endpoints_summary: Optional[Dict[str, Any]]


class ProviderDict(TypedDict):
    """A provider entry in the catalog."""
    
    # Required
    id: str
    display_name: str
    base_url: str
    auth: AuthDict
    capabilities: CapabilitiesDict
    models: List[ModelDict]
    
    # Optional
    source: Optional[SourceDict]
    extra_headers: Optional[Dict[str, str]]


class DefaultsDict(TypedDict, total=False):
    """Default provider and model selection."""
    
    provider_id: Optional[str]
    model_id: Optional[str]


class CatalogDocument(TypedDict):
    """Root ORR Catalog document structure."""
    
    # Required
    schema_version: int
    generated_at: str  # RFC3339 UTC timestamp
    providers: List[ProviderDict]
    
    # Optional
    generator: Optional[str]
    defaults: Optional[DefaultsDict]


# ---------------------------------------------------------------------------
# For backward compatibility and runtime type checking
# ---------------------------------------------------------------------------

# Valid provider IDs
VALID_PROVIDER_IDS: set = {
    PROVIDER_OPENROUTER,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_MISTRAL,
}

# Valid price status values
VALID_PRICE_STATUSES: set = {"known", "free", "dynamic", "unknown"}

# Forbidden keys in auth dict (case-insensitive)
FORBIDDEN_AUTH_KEYS: set = {
    "value", "api_key", "token", "secret", "password",
}

# Forbidden secret patterns (prefixes to scan for in YAML output).
# NOTE: do NOT add "mistral-" here — Mistral model IDs (e.g.
# "mistral-small-latest") legitimately start with that prefix, so it would
# false-positive on every fetched catalog.
FORBIDDEN_SECRET_PATTERNS: list = [
    "sk-or-",
    "sk-",
    "nvapi-",
]


# ---------------------------------------------------------------------------
# Helper type for plugin system
# ---------------------------------------------------------------------------

class ProviderPluginMeta(TypedDict):
    """Metadata returned by a provider plugin."""
    
    display_name: str
    base_url: str
    auth: AuthDict
    capabilities: CapabilitiesDict
    extra_headers: Optional[Dict[str, str]]
