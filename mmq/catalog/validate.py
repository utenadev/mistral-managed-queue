"""Validation functions for ORR Catalog documents.

This module provides validation for catalog documents to ensure they
conform to the ORR Catalog schema specification.
"""

from typing import Any, Dict, List

from mmq.catalog.types import (
    SCHEMA_VERSION,
    VALID_PRICE_STATUSES,
    VALID_PROVIDER_IDS,
)


def validate_catalog(document: Dict[str, Any]) -> List[str]:
    """Validate a catalog document.
    
    Checks:
    - Required fields exist
    - schema_version is supported
    - providers list is valid
    - Each provider has required fields
    - Each model has required fields
    - No duplicate provider IDs
    - No duplicate model IDs within a provider
    
    Args:
        document: The catalog document to validate
        
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    # Check required root fields
    if "schema_version" not in document:
        errors.append("Missing required field: schema_version")
    elif document["schema_version"] != SCHEMA_VERSION:
        errors.append(
            f"Unsupported schema_version: {document['schema_version']} "
            f"(expected {SCHEMA_VERSION})"
        )
    
    if "generated_at" not in document:
        errors.append("Missing required field: generated_at")
    
    if "providers" not in document:
        errors.append("Missing required field: providers")
        return errors
    
    providers = document["providers"]
    if not isinstance(providers, list):
        errors.append("'providers' must be a list")
        return errors
    
    # Validate each provider
    seen_provider_ids = set()
    for i, provider in enumerate(providers):
        provider_errors = _validate_provider(provider, i)
        errors.extend(provider_errors)
        
        # Check for duplicate provider IDs
        provider_id = provider.get("id")
        if provider_id:
            if provider_id in seen_provider_ids:
                errors.append(
                    f"Duplicate provider id '{provider_id}' "
                    f"(first at providers[{i}], duplicate at providers[{i}])"
                )
            seen_provider_ids.add(provider_id)
    
    # Validate defaults if present
    defaults = document.get("defaults")
    if defaults is not None:
        errors.extend(_validate_defaults(defaults, seen_provider_ids))
    
    return errors


def _validate_provider(provider: Dict[str, Any], index: int) -> List[str]:
    """Validate a single provider entry.
    
    Args:
        provider: The provider dict to validate
        index: Index in the providers list (for error messages)
        
    Returns:
        List of error messages
    """
    errors = []
    prefix = f"providers[{index}]"
    
    # Check required fields
    if "id" not in provider:
        errors.append(f"{prefix}: missing required field 'id'")
    elif not isinstance(provider["id"], str):
        errors.append(f"{prefix}: 'id' must be a string")
    
    if "display_name" not in provider:
        errors.append(f"{prefix}: missing required field 'display_name'")
    
    if "base_url" not in provider:
        errors.append(f"{prefix}: missing required field 'base_url'")
    
    # Validate auth
    auth = provider.get("auth")
    if auth is None:
        errors.append(f"{prefix}: missing required field 'auth'")
    elif not isinstance(auth, dict):
        errors.append(f"{prefix}: 'auth' must be a dict")
    else:
        errors.extend(_validate_auth(auth, prefix))
    
    # Validate capabilities
    capabilities = provider.get("capabilities")
    if capabilities is None:
        errors.append(f"{prefix}: missing required field 'capabilities'")
    elif not isinstance(capabilities, dict):
        errors.append(f"{prefix}: 'capabilities' must be a dict")
    else:
        errors.extend(_validate_capabilities(capabilities, prefix))
    
    # Validate models
    models = provider.get("models")
    if models is None:
        errors.append(f"{prefix}: missing required field 'models'")
    elif not isinstance(models, list):
        errors.append(f"{prefix}: 'models' must be a list")
    else:
        errors.extend(_validate_models(models, provider.get("id", "?"), prefix))
    
    # Validate source if present
    source = provider.get("source")
    if source is not None:
        errors.extend(_validate_source(source, prefix))
    
    # Validate extra_headers if present
    extra_headers = provider.get("extra_headers")
    if extra_headers is not None:
        if not isinstance(extra_headers, dict):
            errors.append(f"{prefix}: 'extra_headers' must be a dict or null")
        else:
            # Check for Authorization header
            auth_header_keys = {
                "authorization",
                "api_key",
                "bearer",
                "token",
            }
            for key in extra_headers:
                if key.lower() in auth_header_keys:
                    errors.append(
                        f"{prefix}: forbidden header '{key}' in extra_headers"
                    )
    
    return errors


def _validate_auth(auth: Dict[str, Any], prefix: str) -> List[str]:
    """Validate auth dictionary.
    
    Args:
        auth: The auth dict to validate
        prefix: Path prefix for error messages
        
    Returns:
        List of error messages
    """
    errors = []
    
    if "type" not in auth:
        errors.append(f"{prefix}.auth: missing required field 'type'")
    elif auth["type"] != "bearer_env":
        errors.append(
            f"{prefix}.auth: unsupported type '{auth['type']}' (expected 'bearer_env')"
        )
    
    if "env" not in auth:
        errors.append(f"{prefix}.auth: missing required field 'env'")
    elif not isinstance(auth["env"], str):
        errors.append(f"{prefix}.auth: 'env' must be a string")
    
    # Check for forbidden keys (secrets in value)
    forbidden_value_keys = {"value", "api_key", "token", "secret", "password"}
    for key in auth:
        if key.lower() in forbidden_value_keys:
            errors.append(f"{prefix}.auth: forbidden key '{key}'")
    
    return errors


def _validate_capabilities(capabilities: Dict[str, Any], prefix: str) -> List[str]:
    """Validate capabilities dictionary.
    
    Args:
        capabilities: The capabilities dict to validate
        prefix: Path prefix for error messages
        
    Returns:
        List of error messages
    """
    errors = []
    
    required_keys = {"catalog", "chat"}
    for key in required_keys:
        if key not in capabilities:
            errors.append(f"{prefix}.capabilities: missing required field '{key}'")
        elif not isinstance(capabilities[key], bool):
            errors.append(f"{prefix}.capabilities: '{key}' must be a boolean")
    
    return errors


def _validate_models(models: List[Dict[str, Any]], provider_id: str, prefix: str) -> List[str]:
    """Validate list of models.
    
    Args:
        models: List of model dicts to validate
        provider_id: The provider ID (for error messages)
        prefix: Path prefix for error messages
        
    Returns:
        List of error messages
    """
    errors = []
    seen_ids = set()
    
    for j, model in enumerate(models):
        model_prefix = f"{prefix}.models[{j}]"
        
        # Check required fields
        if "id" not in model:
            errors.append(f"{model_prefix}: missing required field 'id'")
        elif not isinstance(model["id"], str):
            errors.append(f"{model_prefix}: 'id' must be a string")
        else:
            model_id = model["id"]
            if model_id in seen_ids:
                errors.append(
                    f"{model_prefix}: duplicate model id '{model_id}' "
                    f"within provider '{provider_id}'"
                )
            seen_ids.add(model_id)
        
        if "price_status" not in model:
            errors.append(f"{model_prefix}: missing required field 'price_status'")
        elif model["price_status"] not in VALID_PRICE_STATUSES:
            errors.append(
                f"{model_prefix}: invalid price_status '{model['price_status']}' "
                f"(must be one of {VALID_PRICE_STATUSES})"
            )
        
        # Validate optional fields
        optional_numeric_fields = [
            "context_length",
            "prompt_price",
            "completion_price",
            "coding_index",
            "intelligence_index",
        ]
        for field in optional_numeric_fields:
            if field in model and model[field] is not None:
                if not isinstance(model[field], (int, float)):
                    errors.append(
                        f"{model_prefix}: '{field}' must be numeric or null, "
                        f"got {type(model[field]).__name__}"
                    )
        
        optional_string_fields = [
            "name",
            "modality",
            "canonical_slug",
            "expiration_date",
        ]
        for field in optional_string_fields:
            if field in model and model[field] is not None:
                if not isinstance(model[field], str):
                    errors.append(
                        f"{model_prefix}: '{field}' must be string or null, "
                        f"got {type(model[field]).__name__}"
                    )
        
        if "supported_params" in model:
            if model["supported_params"] is None:
                pass  # null is OK
            elif not isinstance(model["supported_params"], list):
                errors.append(
                    f"{model_prefix}: 'supported_params' must be list or null, "
                    f"got {type(model['supported_params']).__name__}"
                )
            else:
                # Check all items are strings
                for k, param in enumerate(model["supported_params"]):
                    if not isinstance(param, str):
                        errors.append(
                            f"{model_prefix}.supported_params[{k}]: "
                            f"must be string, got {type(param).__name__}"
                        )
        
        if "endpoints_summary" in model:
            if model["endpoints_summary"] is not None:
                if not isinstance(model["endpoints_summary"], dict):
                    errors.append(
                        f"{model_prefix}: 'endpoints_summary' must be dict or null"
                    )
    
    return errors


def _validate_source(source: Dict[str, Any], prefix: str) -> List[str]:
    """Validate source dictionary.
    
    Args:
        source: The source dict to validate
        prefix: Path prefix for error messages
        
    Returns:
        List of error messages
    """
    errors = []
    
    if "list_endpoint" not in source:
        errors.append(f"{prefix}.source: missing recommended field 'list_endpoint'")
    
    if "fetched_at" not in source:
        errors.append(f"{prefix}.source: missing recommended field 'fetched_at'")
    
    if "warnings" in source and source["warnings"] is not None:
        if not isinstance(source["warnings"], list):
            errors.append(f"{prefix}.source: 'warnings' must be list or null")
        else:
            for k, warning in enumerate(source["warnings"]):
                if not isinstance(warning, str):
                    errors.append(
                        f"{prefix}.source.warnings[{k}]: must be string"
                    )
    
    if "error" in source and source["error"] is not None:
        if not isinstance(source["error"], str):
            errors.append(f"{prefix}.source: 'error' must be string or null")
    
    return errors


def _validate_defaults(defaults: Dict[str, Any], valid_providers: set) -> List[str]:
    """Validate defaults dictionary.
    
    Args:
        defaults: The defaults dict to validate
        valid_providers: Set of valid provider IDs
        
    Returns:
        List of error messages
    """
    errors = []
    
    provider_id = defaults.get("provider_id")
    if provider_id is not None:
        if not isinstance(provider_id, str):
            errors.append("'defaults.provider_id' must be string or null")
        elif provider_id not in valid_providers:
            errors.append(
                f"'defaults.provider_id' '{provider_id}' not found in providers"
            )
    
    model_id = defaults.get("model_id")
    if model_id is not None:
        if not isinstance(model_id, str):
            errors.append("'defaults.model_id' must be string or null")
    
    return errors
