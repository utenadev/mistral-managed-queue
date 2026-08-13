"""Mistral provider plugin for catalog fetching.

This plugin fetches model information from the Mistral API
and normalizes it to the ORR Catalog format.

Mistral provides models at https://api.mistral.ai/v1/models
with the mistralai Python SDK.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from mmq.catalog.adapters.base import BaseProviderPlugin
from mmq.catalog.types import (
    ModelDict,
    PROVIDER_MISTRAL,
    ProviderPluginMeta,
)


# Mistral API base URL
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

# Free-tier models for Mistral (P1 allowlist)
MISTRAL_FREE_MODELS = {
    "mistral-small-latest",
    "mistral-medium-latest",
    "mistral-tiny-latest",
    "mistral-large-latest",  # Note: large may not always be free
}

# Default headers for Mistral API
MISTRAL_DEFAULT_HEADERS = {}


class MistralPlugin(BaseProviderPlugin):
    """Plugin for fetching and normalizing Mistral model catalog.
    
    This plugin:
    - Fetches models from GET /v1/models or via mistralai SDK
    - Normalizes price fields (0 -> free)
    - Determines free models via allowlist or price check
    - Applies rate gate (shares with NIM)
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        use_rate_gate: bool = True,  # Apply rate gate for Mistral
        include_endpoints_summary: bool = False,
    ):
        """Initialize the Mistral plugin.
        
        Args:
            base_url: Override the Mistral API base URL
            api_key: Mistral API key (required for listing)
            use_rate_gate: Whether to use the shared rate gate (default True)
            include_endpoints_summary: Whether to fetch endpoints details
        """
        super().__init__(use_rate_gate=use_rate_gate)
        self.base_url = base_url or MISTRAL_BASE_URL
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY")
        self.include_endpoints_summary = include_endpoints_summary
    
    @property
    def provider_id(self) -> str:
        return PROVIDER_MISTRAL
    
    def provider_meta(self) -> ProviderPluginMeta:
        return {
            "display_name": "Mistral",
            "base_url": self.base_url,
            "auth": {
                "type": "bearer_env",
                "env": "MISTRAL_API_KEY",
            },
            "capabilities": {
                "catalog": True,
                "chat": False,  # P1: chat not supported yet via catalog
            },
            "extra_headers": None,
        }
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = dict(MISTRAL_DEFAULT_HEADERS)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def list_raw_models(self) -> List[Dict[str, Any]]:
        """Fetch raw model list from Mistral API.
        
        GET /v1/models returns model list.
        Requires API key.
        
        Returns:
            List of raw model dictionaries.
            
        Raises:
            Exception: If the API call fails.
        """
        if not self.api_key:
            raise ValueError(
                "MISTRAL_API_KEY is required for Mistral catalog fetch. "
                "Set MISTRAL_API_KEY environment variable or provide api_key."
            )
        
        # Apply rate gate before API call
        self._apply_rate_gate()
        
        url = f"{self.base_url}/models"
        headers = self._get_headers()
        
        try:
            response = httpx.get(url, headers=headers, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            
            # Mistral returns { "data": [...] }
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            elif isinstance(data, list):
                return data
            else:
                raise ValueError(f"Unexpected response format from Mistral /models")
                
        except httpx.HTTPStatusError as e:
            raise Exception(f"Mistral API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Mistral request failed: {e}")
    
    def normalize_model(self, raw: Dict[str, Any]) -> ModelDict:
        """Normalize Mistral raw model to ORR Catalog format.
        
        Field mapping:
        - id: raw["id"]
        - name: raw["name"] or raw["id"]
        - context_length: raw["context_length"] or None
        - modality: raw["modality"] or None
        - prompt_price: raw["pricing"]["prompt"] or 0 if free
        - completion_price: raw["pricing"]["completion"] or 0 if free
        - price_status: based on price values
        """
        model_id = raw.get("id") or "unknown"
        name = raw.get("name") or model_id
        
        # Extract pricing - Mistral may return different formats
        pricing = raw.get("pricing", {})
        
        def normalize_price(val: Any) -> Optional[float]:
            if val is None:
                return None
            if isinstance(val, str):
                if val == "0":
                    return 0.0
                try:
                    return float(val)
                except ValueError:
                    return None
            if isinstance(val, (int, float)):
                return float(val)
            return None
        
        prompt_price = normalize_price(pricing.get("prompt"))
        completion_price = normalize_price(pricing.get("completion"))
        
        # Determine price_status
        def determine_price_status(prompt: Optional[float], completion: Optional[float]) -> str:
            if prompt is not None and completion is not None:
                if prompt == 0.0 and completion == 0.0:
                    return "free"
                if prompt >= 0 and completion >= 0:
                    return "known"
            # If either is None, we don't know
            if prompt is None or completion is None:
                return "unknown"
            return "known"
        
        price_status = determine_price_status(prompt_price, completion_price)
        
        # Extract context length from different possible locations
        context_length = raw.get("context_length")
        if context_length is None:
            # Some Mistral responses use max_tokens
            context_length = raw.get("max_tokens")
        
        model: ModelDict = {
            "id": model_id,
            "name": name,
            "price_status": price_status,
            "prompt_price": prompt_price,
            "completion_price": completion_price,
            "context_length": context_length,
            "modality": raw.get("modality"),
            "canonical_slug": None,
            "coding_index": None,
            "intelligence_index": None,
            "expiration_date": None,
            "supported_params": [],
        }
        
        return model
    
    def is_free(self, normalized: ModelDict, raw: Dict[str, Any]) -> bool:
        """Check if Mistral model is free.
        
        A model is considered free if:
        - price_status is "free" (both prompt and completion are 0)
        - OR the model ID is in the free allowlist
        """
        if normalized.get("price_status") == "free":
            return True
        
        model_id = normalized.get("id", "")
        if model_id in MISTRAL_FREE_MODELS:
            return True
        
        return False
    
    def fetch_model_details(
        self,
        model_id: str,
        raw: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Mistral doesn't have endpoints API like OpenRouter.
        
        Returns None always for P1.
        """
        return None
