"""Core catalog fetching logic.

This module provides the main fetch_catalog function that coordinates
all provider plugins to build the ORR Catalog document.

See docs/DESIGN_model-catalog_detail.md for the fetch design specification.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mmq.catalog.adapters import (
    OpenRouterPlugin,
    NvidiaNimPlugin,
    MistralPlugin,
)
from mmq.catalog.adapters.base import ProviderPlugin, CATALOG_BASE_WAIT_TIME
from mmq.catalog.types import (
    CatalogDocument,
    FORBIDDEN_AUTH_KEYS,
    FORBIDDEN_SECRET_PATTERNS,
    ModelDict,
    PROVIDER_OPENROUTER,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_MISTRAL,
    ProviderDict,
    SCHEMA_VERSION,
    SourceDict,
)
from mmq.catalog.validate import validate_catalog



def _get_timestamp() -> str:
    """Get current UTC timestamp in RFC3339 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

logger = logging.getLogger("mmq.catalog")


@dataclass
class FetchResult:
    """Result of a catalog fetch operation.
    
    Attributes:
        document: The complete ORR Catalog document (YAML-compatible dict)
        errors: List of error messages for failed providers
        partial: True if some providers succeeded and some failed
    """
    
    document: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    partial: bool = False


# Default provider list (order matters for default selection)
DEFAULT_PROVIDERS: List[str] = [
    PROVIDER_OPENROUTER,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_MISTRAL,
]

# Provider ID to Plugin class mapping
PROVIDER_PLUGIN_MAP: Dict[str, type] = {
    PROVIDER_OPENROUTER: OpenRouterPlugin,
    PROVIDER_NVIDIA_NIM: NvidiaNimPlugin,
    PROVIDER_MISTRAL: MistralPlugin,
}


def get_plugin_instance(
    provider_id: str,
    use_rate_gate: bool = True,
    include_endpoints_summary: bool = False,
) -> ProviderPlugin:
    """Create and return a plugin instance for the given provider.
    
    Args:
        provider_id: The provider identifier
        use_rate_gate: Whether to use rate gating
        include_endpoints_summary: Whether to include endpoints summary
        
    Returns:
        A ProviderPlugin instance
        
    Raises:
        ValueError: If the provider_id is not recognized
    """
    plugin_class = PROVIDER_PLUGIN_MAP.get(provider_id)
    if plugin_class is None:
        raise ValueError(f"Unknown provider: {provider_id}")
    
    return plugin_class(
        use_rate_gate=use_rate_gate,
        include_endpoints_summary=include_endpoints_summary,
    )


def _scan_for_secrets(data: Any, path: str = "root") -> List[str]:
    """Recursively scan data structure for forbidden secret patterns.
    
    Args:
        data: The data to scan
        path: Current path in the data structure (for error messages)
        
    Returns:
        List of error messages describing found secrets
    """
    errors = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            # Check for forbidden auth keys (case-insensitive)
            if key.lower() in FORBIDDEN_AUTH_KEYS:
                errors.append(f"Forbidden auth key '{key}' found at {path}.{key}")
            
            # Recursively scan value
            errors.extend(_scan_for_secrets(value, f"{path}.{key}"))
            
            # Check string values for secret patterns
            if isinstance(value, str):
                for pattern in FORBIDDEN_SECRET_PATTERNS:
                    if value.startswith(pattern):
                        errors.append(
                            f"Potential secret detected (starts with '{pattern}') "
                            f"at {path}.{key}"
                        )
                        
    elif isinstance(data, list):
        for i, item in enumerate(data):
            errors.extend(_scan_for_secrets(item, f"{path}[{i}]"))
            
    elif isinstance(data, str):
        for pattern in FORBIDDEN_SECRET_PATTERNS:
            if data.startswith(pattern):
                errors.append(
                    f"Potential secret detected (starts with '{pattern}') at {path}"
                )
    
    return errors


def _scan_auth_secrets(auth_dict: Dict[str, Any]) -> List[str]:
    """Scan auth dictionary specifically for secret values.
    
    Checks that auth dict doesn't contain actual secret values.
    
    Args:
        auth_dict: The auth dictionary to scan
        
    Returns:
        List of error messages if secrets found
    """
    errors = []
    
    # Check for forbidden keys
    for key in auth_dict:
        if key.lower() in FORBIDDEN_AUTH_KEYS:
            errors.append(f"Forbidden auth key: '{key}'")
    
    # Check values for secret patterns
    for key, value in auth_dict.items():
        if isinstance(value, str):
            for pattern in FORBIDDEN_SECRET_PATTERNS:
                if value.startswith(pattern):
                    errors.append(
                        f"Secret value detected in auth.{key} (starts with '{pattern}')"
                    )
    
    return errors


def _validate_provider_models(
    provider_id: str,
    models: List[ModelDict]
) -> List[str]:
    """Validate models for a provider.
    
    Checks:
    - Each model has required 'id' field
    - Each model has required 'price_status' field
    - Model IDs are unique within the provider
    
    Args:
        provider_id: The provider identifier
        models: List of model dicts
        
    Returns:
        List of error messages
    """
    errors = []
    seen_ids = set()
    
    for i, model in enumerate(models):
        if "id" not in model:
            errors.append(f"Provider {provider_id}: model[{i}] missing required 'id' field")
        elif model["id"] in seen_ids:
            errors.append(
                f"Provider {provider_id}: duplicate model id '{model['id']}'"
            )
        else:
            seen_ids.add(model["id"])
        
        if "price_status" not in model:
            errors.append(
                f"Provider {provider_id}: model[{i}] ({model.get('id', '?')}) "
                "missing required 'price_status' field"
            )
    
    return errors


def _validate_provider_aunth(
    provider: ProviderDict
) -> List[str]:
    """Validate provider authentication configuration.
    
    Checks:
    - auth dict exists and has required fields
    - auth dict doesn't contain secret values
    
    Args:
        provider: The provider dict
        
    Returns:
        List of error messages
    """
    errors = []
    
    auth = provider.get("auth")
    if auth is None:
        errors.append(f"Provider {provider['id']}: missing 'auth' field")
        return errors
    
    if not isinstance(auth, dict):
        errors.append(f"Provider {provider['id']}: 'auth' must be a dict")
        return errors
    
    # Check required auth fields
    if "type" not in auth:
        errors.append(f"Provider {provider['id']}: auth missing 'type' field")
    if "env" not in auth:
        errors.append(f"Provider {provider['id']}: auth missing 'env' field")
    
    # Scan for secrets in auth
    errors.extend(_scan_auth_secrets(auth))
    
    return errors


def _build_source_dict(
    plugin: ProviderPlugin,
    list_endpoint: str,
    error: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> SourceDict:
    """Build source metadata for a provider.
    
    Args:
        plugin: The provider plugin
        list_endpoint: The API endpoint used
        error: Optional error message if fetch failed
        warnings: Optional list of warnings
        
    Returns:
        SourceDict with metadata
    """
    return {
        "list_endpoint": list_endpoint,
        "fetched_at": _get_timestamp(),
        "warnings": warnings or [],
        "error": error,
    }


def fetch_catalog(
    *,
    providers: Optional[List[str]] = None,
    free_only: bool = True,
    include_endpoints_summary: bool = False,
    use_rate_gate: bool = True,
    base_urls: Optional[Dict[str, str]] = None,
    validate: bool = True,
) -> FetchResult:
    """Fetch catalog from all configured providers.
    
    This is the main entry point for fetching the ORR Catalog.
    
    Args:
        providers: List of provider IDs to fetch (default: all known providers)
        free_only: If True, only include models that are free (default: True)
        include_endpoints_summary: If True, fetch endpoints summary for models
        use_rate_gate: Whether to apply the shared rate gate between providers
        base_urls: Optional dict of provider_id -> base_url overrides
        validate: If False, skip catalog validation (default: True).
            The security secret scan still always runs.
        
    Returns:
        FetchResult with the complete catalog document, errors, and partial flag
    """
    # Determine which providers to fetch
    if providers is None:
        providers = DEFAULT_PROVIDERS[:]
    
    # Build plugin instances
    plugin_instances = []
    for provider_id in providers:
        try:
            plugin_class = PROVIDER_PLUGIN_MAP.get(provider_id)
            if plugin_class is None:
                raise ValueError(f"Unknown provider: {provider_id}")
            
            # Get base_url override if provided
            base_url = base_urls.get(provider_id) if base_urls else None
            
            plugin = plugin_class(
                base_url=base_url,
                use_rate_gate=use_rate_gate,
                include_endpoints_summary=include_endpoints_summary,
            )
            plugin_instances.append(plugin)
        except Exception as e:
            # This will be handled in the fetch loop
            pass
    
    # Track results
    providers_out: List[ProviderDict] = []
    all_errors: List[str] = []
    has_success = False
    has_failure = False
    
    # Determine list_endpoint for each provider
    # This is used in source metadata
    provider_list_endpoints = {
        PROVIDER_OPENROUTER: "/models",
        PROVIDER_NVIDIA_NIM: "/models",
        PROVIDER_MISTRAL: "models",  # Mistral uses different path
    }
    
    # Fetch from each provider
    for i, plugin in enumerate(plugin_instances):
        provider_id = plugin.provider_id
        list_endpoint = provider_list_endpoints.get(provider_id, "/models")
        
        # Apply rate gate between providers (not before first)
        if use_rate_gate and i > 0:
            logger.info(f"Rate gating: waiting {CATALOG_BASE_WAIT_TIME}s before fetching from {provider_id}")
            time.sleep(CATALOG_BASE_WAIT_TIME)
        
        try:
            # List raw models from provider
            raw_models = plugin.list_raw_models()
            
            # Normalize and filter models
            models: List[ModelDict] = []
            provider_warnings: List[str] = []
            
            for raw in raw_models:
                try:
                    normalized = plugin.normalize_model(raw)
                    
                    # Apply free filter if requested
                    if free_only and not plugin.is_free(normalized, raw):
                        continue
                    
                    # Optionally fetch details
                    if include_endpoints_summary:
                        details = plugin.fetch_model_details(
                            normalized["id"],
                            raw
                        )
                        if details:
                            normalized["endpoints_summary"] = details
                    
                    models.append(normalized)
                    
                except Exception as e:
                    # Skip individual model errors, log warning
                    model_id = raw.get("id", "unknown")
                    warning = f"Failed to normalize model {model_id}: {e}"
                    provider_warnings.append(warning)
                    logger.warning(warning)
            
            # Build provider dict
            provider_meta = plugin.provider_meta()
            
            provider: ProviderDict = {
                "id": provider_id,
                "display_name": provider_meta["display_name"],
                "base_url": provider_meta["base_url"],
                "auth": provider_meta["auth"],
                "capabilities": provider_meta["capabilities"],
                "models": models,
                "source": _build_source_dict(
                    plugin,
                    list_endpoint,
                    error=None,
                    warnings=provider_warnings if provider_warnings else None,
                ),
            }
            
            # Add extra_headers if present
            extra_headers = provider_meta.get("extra_headers")
            if extra_headers:
                provider["extra_headers"] = extra_headers
            
            providers_out.append(provider)
            has_success = True
            
            if provider_warnings:
                logger.info(
                    f"Provider {provider_id}: {len(provider_warnings)} warnings, "
                    f"{len(models)} models"
                )
            else:
                logger.info(f"Provider {provider_id}: {len(models)} models")
                
        except Exception as e:
            # Provider fetch failed entirely
            error_msg = f"Provider {provider_id} failed: {e}"
            all_errors.append(error_msg)
            has_failure = True
            logger.error(error_msg)
            
            # Add provider with empty models and error in source
            provider_meta = plugin.provider_meta()
            providers_out.append({
                "id": provider_id,
                "display_name": provider_meta["display_name"],
                "base_url": provider_meta["base_url"],
                "auth": provider_meta["auth"],
                "capabilities": provider_meta["capabilities"],
                "models": [],
                "source": _build_source_dict(
                    plugin,
                    list_endpoint,
                    error=str(e),
                    warnings=None,
                ),
            })
    
    # Build defaults
    # Try to use first provider's first model as default
    defaults = {}
    if providers_out:
        for provider in providers_out:
            if provider["models"]:
                defaults = {
                    "provider_id": provider["id"],
                    "model_id": provider["models"][0]["id"],
                }
                break
    
    # Build the catalog document
    document: CatalogDocument = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _get_timestamp(),
        "generator": "mmq.catalog.fetch_catalog",
        "defaults": defaults if defaults else None,
        "providers": providers_out,
    }
    
    # Scan for secrets in the document
    secret_errors = _scan_for_secrets(document)
    if secret_errors:
        all_errors.extend(secret_errors)
        logger.error("Secret scan found issues:")
        for err in secret_errors:
            logger.error(f"  - {err}")
    
    # Validate the document
    if validate:
        validation_errors = validate_catalog(document)
        if validation_errors:
            all_errors.extend(validation_errors)
            logger.error("Validation errors:")
            for err in validation_errors:
                logger.error(f"  - {err}")
    
    return FetchResult(
        document=document,
        errors=all_errors,
        partial=has_success and has_failure,
    )
