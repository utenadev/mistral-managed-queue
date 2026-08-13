"""Base provider plugin protocol and abstract class.

This module defines the ProviderPlugin protocol that all provider
adapters must implement.

See docs/DESIGN_model-catalog_detail.md for the plugin design specification.
"""

import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from mmq.catalog.types import (
    ModelDict,
    ProviderPluginMeta,
)


@runtime_checkable
class ProviderPlugin(Protocol):
    """Protocol defining the interface for provider plugins.
    
    All provider plugins must implement these methods.
    The core fetch_catalog function will call these methods
    in sequence for each registered plugin.
    
    P1 Implementation: OpenRouterPlugin, NvidiaNimPlugin, MistralPlugin
    """
    
    @property
    def provider_id(self) -> str:
        """Unique provider identifier (e.g., 'openrouter', 'nvidia_nim', 'mistral')."""
        ...
    
    def provider_meta(self) -> ProviderPluginMeta:
        """Return provider metadata for the catalog.
        
        Returns:
            Dictionary with display_name, base_url, auth, capabilities, extra_headers.
        """
        ...
    
    def list_raw_models(self) -> List[Dict[str, Any]]:
        """Fetch raw model list from the provider API.
        
        Returns:
            List of raw model dictionaries as returned by the provider API.
            
        Raises:
            Exception: If the API call fails. The caller (fetch_catalog)
                      will catch this and mark the provider as failed.
        """
        ...
    
    def normalize_model(self, raw: Dict[str, Any]) -> ModelDict:
        """Normalize a raw model dictionary to ORR Catalog model format.
        
        This includes:
        - Mapping raw fields to catalog fields
        - Price normalization ("0" -> free, "-1" -> dynamic, etc.)
        - Default values for missing fields
        
        Args:
            raw: Raw model dictionary from list_raw_models()
            
        Returns:
            Normalized ModelDict for the catalog.
        """
        ...
    
    def is_free(self, normalized: ModelDict, raw: Dict[str, Any]) -> bool:
        """Determine if a model should be included when free_only=True.
        
        The definition of "free" is provider-specific:
        - OpenRouter: price_status == "free" (or id contains ":free")
        - NVIDIA NIM: All listed models are assumed free (for P1)
        - Mistral: Allowlist of free-tier models
        
        Args:
            normalized: The normalized model dict
            raw: The original raw model dict (for reference)
            
        Returns:
            True if this model should be included in free-only mode.
        """
        ...
    
    def fetch_model_details(
        self,
        model_id: str,
        raw: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch optional detailed information for a model.
        
        This is called only when include_endpoints_summary=True.
        It can fetch heavy details like endpoints, uptime, etc.
        
        Args:
            model_id: The model ID to fetch details for
            raw: Optional raw model dict (from list_raw_models)
            
        Returns:
            Optional dictionary with additional details (e.g., endpoints_summary),
            or None if not available/implemented.
        """
        ...


class BaseProviderPlugin(ABC):
    """Abstract base class for provider plugins.
    
    Provides common functionality and defaults for provider plugins.
    Subclasses should override the abstract methods.
    """
    
    # Rate limiting constants for catalog fetching
    # Separate from chat API rate limiting; can be tuned via MMQ_CATALOG_* env vars
    CATALOG_BASE_WAIT_TIME = float(os.environ.get(
        "MMQ_CATALOG_BASE_WAIT_TIME",
        os.environ.get("MMQ_BASE_WAIT_TIME", "31.0")
    ))
    
    def __init__(self, use_rate_gate: bool = True):
        """Initialize the plugin.
        
        Args:
            use_rate_gate: Whether to respect the shared rate gate
                           (from mmq's BASE_WAIT_TIME mechanism).
        """
        self.use_rate_gate = use_rate_gate
        self._last_request_time: float = 0.0
    
    def _apply_rate_gate(self) -> None:
        """Apply rate gating before making API calls.
        
        This implements a simple time-based rate gate that waits
        CATALOG_BASE_WAIT_TIME seconds between API calls.
        """
        if not self.use_rate_gate:
            return
        
        elapsed = time.time() - self._last_request_time
        if elapsed < self.CATALOG_BASE_WAIT_TIME:
            wait_time = self.CATALOG_BASE_WAIT_TIME - elapsed
            time.sleep(wait_time)
        
        self._last_request_time = time.time()
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier."""
        ...
    
    @abstractmethod
    def provider_meta(self) -> ProviderPluginMeta:
        """Return provider metadata."""
        ...
    
    @abstractmethod
    def list_raw_models(self) -> List[Dict[str, Any]]:
        """Fetch raw model list."""
        ...
    
    @abstractmethod
    def normalize_model(self, raw: Dict[str, Any]) -> ModelDict:
        """Normalize a raw model to catalog format."""
        ...
    
    @abstractmethod
    def is_free(self, normalized: ModelDict, raw: Dict[str, Any]) -> bool:
        """Check if model is free."""
        ...
    
    def fetch_model_details(
        self,
        model_id: str,
        raw: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Default implementation returns None (no details)."""
        return None
    
    def _get_timestamp(self) -> str:
        """Get current UTC timestamp in RFC3339 format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
