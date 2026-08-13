"""NVIDIA NIM provider plugin for catalog fetching.

This plugin fetches model information from the NVIDIA NIM API
and normalizes it to the ORR Catalog format.

NVIDIA NIM provides models at https://integrate.api.nvidia.com/v1/models
without requiring authentication for listing (but requires API key for usage).
"""

import os
from typing import Any, Dict, List, Optional

import httpx

from mmq.catalog.adapters.base import BaseProviderPlugin
from mmq.catalog.types import (
    ModelDict,
    PROVIDER_NVIDIA_NIM,
    ProviderPluginMeta,
)


# NVIDIA NIM API base URL
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaNimPlugin(BaseProviderPlugin):
    """Plugin for fetching and normalizing NVIDIA NIM model catalog.
    
    This plugin:
    - Fetches models from GET /v1/models
    - Sets price_status to "unknown" (NIM doesn't provide pricing via API)
    - P1: Treats all listed models as free (for catalog purposes)
    - Does not fetch endpoints summary (not applicable for NIM)
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        use_rate_gate: bool = True,  # Apply rate gate for NIM (share with Mistral)
        include_endpoints_summary: bool = False,
    ):
        """Initialize the NVIDIA NIM plugin.
        
        Args:
            base_url: Override the NIM API base URL
            api_key: NVIDIA API key (optional for listing)
            use_rate_gate: Whether to use the shared rate gate
            include_endpoints_summary: Whether to fetch endpoints details
        """
        super().__init__(use_rate_gate=use_rate_gate)
        self.base_url = base_url or NVIDIA_NIM_BASE_URL
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        self.include_endpoints_summary = include_endpoints_summary
    
    @property
    def provider_id(self) -> str:
        return PROVIDER_NVIDIA_NIM
    
    def provider_meta(self) -> ProviderPluginMeta:
        return {
            "display_name": "NVIDIA NIM",
            "base_url": self.base_url,
            "auth": {
                "type": "bearer_env",
                "env": "NVIDIA_API_KEY",
            },
            "capabilities": {
                "catalog": True,
                "chat": False,  # P1: chat not supported yet
            },
            "extra_headers": None,
        }
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def list_raw_models(self) -> List[Dict[str, Any]]:
        """Fetch raw model list from NVIDIA NIM API.
        
        GET /v1/models returns model list.
        
        Returns:
            List of raw model dictionaries.
            
        Raises:
            Exception: If the API call fails.
        """
        # Apply rate gate before API call
        self._apply_rate_gate()
        
        url = f"{self.base_url}/models"
        headers = self._get_headers()
        
        try:
            response = httpx.get(url, headers=headers, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            
            # NIM returns list directly
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            else:
                raise ValueError(f"Unexpected response format from NVIDIA NIM /models")
                
        except httpx.HTTPStatusError as e:
            raise Exception(f"NVIDIA NIM API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"NVIDIA NIM request failed: {e}")
    
    def normalize_model(self, raw: Dict[str, Any]) -> ModelDict:
        """Normalize NVIDIA NIM raw model to ORR Catalog format.
        
        NIM doesn't provide pricing via API, so:
        - prompt_price: None
        - completion_price: None
        - price_status: "unknown"
        
        Field mapping:
        - id: raw["id"] or raw["model_id"]
        - name: raw["name"] or raw["id"]
        - context_length: raw["context_length"] or None
        - modality: raw["modality"] or None
        - supported_params: raw["supported_params"] or []
        """
        model_id = raw.get("id") or raw.get("model_id")
        if not model_id:
            model_id = "unknown"
        
        name = raw.get("name") or raw.get("id") or model_id
        
        # NIM doesn't provide pricing via API
        model: ModelDict = {
            "id": model_id,
            "name": name,
            "price_status": "unknown",
            "prompt_price": None,
            "completion_price": None,
            "context_length": raw.get("context_length"),
            "modality": raw.get("modality"),
            "canonical_slug": None,
            "coding_index": None,
            "intelligence_index": None,
            "expiration_date": None,
            "supported_params": [],
        }
        
        return model
    
    def is_free(self, normalized: ModelDict, raw: Dict[str, Any]) -> bool:
        """Check if NVIDIA NIM model is free.
        
        P1: All listed models are assumed to be free for catalog purposes.
        This is because NIM doesn't provide pricing via API.
        
        In the future, we may use an allowlist approach.
        """
        # P1: All NIM models are considered free for catalog
        return True
    
    def fetch_model_details(
        self,
        model_id: str,
        raw: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """NVIDIA NIM doesn't have endpoints API like OpenRouter.
        
        Returns None always.
        """
        return None
