"""OpenRouter provider plugin for catalog fetching.

This plugin fetches model information from the OpenRouter API
and normalizes it to the ORR Catalog format.

See docs/model-catalog.md for OpenRouter API field details.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from mmq.catalog.adapters.base import BaseProviderPlugin
from mmq.catalog.types import (
    ModelDict,
    PROVIDER_OPENROUTER,
    ProviderPluginMeta,
)


# OpenRouter API base URL
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default headers for OpenRouter API
OPENROUTER_DEFAULT_HEADERS = {
    "HTTP-Referer": "https://github.com/utenadev/orr",
    "X-Title": "orr",
}


class OpenRouterPlugin(BaseProviderPlugin):
    """Plugin for fetching and normalizing OpenRouter model catalog.
    
    This plugin:
    - Fetches models from GET /api/v1/models
    - Normalizes price fields ("0" -> free, "-1" -> dynamic)
    - Determines free models (price_status == "free" or id contains ":free")
    - Optionally fetches endpoints summary for models
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        use_rate_gate: bool = False,  # OR /models is lightweight, can bypass
        include_endpoints_summary: bool = False,
    ):
        """Initialize the OpenRouter plugin.
        
        Args:
            base_url: Override the OpenRouter API base URL
            api_key: OpenRouter API key (optional - /models works without it)
            use_rate_gate: Whether to use the shared rate gate (default False for OR)
            include_endpoints_summary: Whether to fetch endpoints details
        """
        super().__init__(use_rate_gate=use_rate_gate)
        self.base_url = base_url or OPENROUTER_BASE_URL
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.include_endpoints_summary = include_endpoints_summary
    
    @property
    def provider_id(self) -> str:
        return PROVIDER_OPENROUTER
    
    def provider_meta(self) -> ProviderPluginMeta:
        return {
            "display_name": "OpenRouter",
            "base_url": self.base_url,
            "auth": {
                "type": "bearer_env",
                "env": "OPENROUTER_API_KEY",
            },
            "capabilities": {
                "catalog": True,
                "chat": True,
            },
            "extra_headers": OPENROUTER_DEFAULT_HEADERS,
        }
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = dict(OPENROUTER_DEFAULT_HEADERS)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def list_raw_models(self) -> List[Dict[str, Any]]:
        """Fetch raw model list from OpenRouter API.
        
        GET /api/v1/models returns all models.
        This endpoint works without authentication.
        
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
            # Note: /models works without auth, so we don't require api_key
            response = httpx.get(url, headers=headers, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            
            # OpenRouter returns { "data": [...] } for /models
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            elif isinstance(data, list):
                return data
            else:
                raise ValueError(f"Unexpected response format from OpenRouter /models")
                
        except httpx.HTTPStatusError as e:
            raise Exception(f"OpenRouter API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"OpenRouter request failed: {e}")
    
    def normalize_model(self, raw: Dict[str, Any]) -> ModelDict:
        """Normalize OpenRouter raw model to ORR Catalog format.
        
        Field mapping:
        - id: raw["id"]
        - name: raw["name"]
        - context_length: raw["context_length"]
        - modality: raw["architecture"]["modality"] or raw["modality"]
        - canonical_slug: raw["canonical_slug"]
        - prompt_price: normalized from raw["pricing"]["prompt"]
        - completion_price: normalized from raw["pricing"]["completion"]
        - price_status: determined from price values
        - coding_index: raw["benchmarks"]["artificial_analysis"]["coding_index"]
        - intelligence_index: raw["benchmarks"]["artificial_analysis"]["intelligence_index"]
        - expiration_date: raw["expiration_date"]
        - supported_params: raw["supported_parameters"]
        """
        # Extract pricing
        pricing = raw.get("pricing", {})
        
        # Normalize price values
        prompt_price_raw = pricing.get("prompt")
        completion_price_raw = pricing.get("completion")
        
        # Handle string prices like "0" or "-1"
        def normalize_price(val: Any) -> Optional[float]:
            if val is None:
                return None
            if isinstance(val, str):
                if val == "0":
                    return 0.0
                if val == "-1":
                    return None  # dynamic pricing
                try:
                    return float(val)
                except ValueError:
                    return None
            if isinstance(val, (int, float)):
                return float(val)
            return None
        
        prompt_price = normalize_price(prompt_price_raw)
        completion_price = normalize_price(completion_price_raw)
        
        # Determine price_status
        def determine_price_status(prompt: Optional[float], completion: Optional[float]) -> str:
            if prompt is not None and completion is not None:
                if prompt == 0.0 and completion == 0.0:
                    return "free"
                if prompt >= 0 and completion >= 0:
                    return "known"
            # Check for dynamic pricing (both None or one None)
            if prompt is None or completion is None:
                return "dynamic"
            return "known"
        
        price_status = determine_price_status(prompt_price, completion_price)
        
        # Extract benchmark indices
        benchmarks = raw.get("benchmarks", {})
        artificial_analysis = benchmarks.get("artificial_analysis", {})
        coding_index = artificial_analysis.get("coding_index")
        intelligence_index = artificial_analysis.get("intelligence_index")
        
        # Extract modality
        modality = None
        architecture = raw.get("architecture", {})
        if isinstance(architecture, dict):
            modality = architecture.get("modality")
        if modality is None:
            modality = raw.get("modality")  # fallback
        
        # Extract supported parameters
        supported_params = raw.get("supported_parameters", [])
        if supported_params is None:
            supported_params = []
        
        model: ModelDict = {
            "id": raw["id"],
            "name": raw.get("name", raw["id"]),
            "price_status": price_status,
            "prompt_price": prompt_price,
            "completion_price": completion_price,
            "context_length": raw.get("context_length"),
            "modality": modality,
            "canonical_slug": raw.get("canonical_slug"),
            "coding_index": float(coding_index) if coding_index is not None else None,
            "intelligence_index": float(intelligence_index) if intelligence_index is not None else None,
            "expiration_date": raw.get("expiration_date"),
            "supported_params": list(supported_params) if isinstance(supported_params, list) else [],
        }
        
        return model
    
    def is_free(self, normalized: ModelDict, raw: Dict[str, Any]) -> bool:
        """Check if OpenRouter model is free.
        
        A model is considered free if:
        - price_status is "free" (both prompt and completion are 0)
        - OR the model ID contains ":free" (some providers use this convention)
        """
        if normalized.get("price_status") == "free":
            return True
        
        model_id = normalized.get("id", "")
        if ":free" in model_id:
            return True
        
        return False
    
    def fetch_model_details(
        self,
        model_id: str,
        raw: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch endpoints summary for a model.
        
        GET /api/v1/models/{model_id}/endpoints
        
        This returns provider information including uptime, latency, etc.
        We summarize this into a compact endpoints_summary dict.
        
        Args:
            model_id: The model ID (canonical slug)
            raw: Optional raw model dict
            
        Returns:
            endpoints_summary dict or None
        """
        if not self.include_endpoints_summary:
            return None
        
        url = f"{self.base_url}/models/{model_id}/endpoints"
        headers = self._get_headers()
        
        try:
            response = httpx.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list):
                return None
            
            # Summarize endpoints data
            if len(data) == 0:
                return None
            
            uptime_values = []
            provider_names = set()
            
            for endpoint in data:
                if isinstance(endpoint, dict):
                    if "provider_name" in endpoint:
                        provider_names.add(endpoint["provider_name"])
                    if "uptime_last_1d" in endpoint:
                        uptime = endpoint["uptime_last_1d"]
                        if uptime is not None:
                            try:
                                uptime_values.append(float(uptime))
                            except (ValueError, TypeError):
                                pass
            
            summary: Dict[str, Any] = {
                "provider_count": len(provider_names),
            }
            
            if uptime_values:
                summary["best_uptime_1d"] = max(uptime_values)
            
            return summary
            
        except Exception as e:
            # Log but don't fail - endpoints are optional
            return None
