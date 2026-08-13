"""YAML writing utilities for ORR Catalog.

This module provides functions for writing the catalog document
to YAML files with proper security checks and file permissions.
"""

import os
import pathlib
from typing import Any, Dict

import yaml

from mmq.catalog.types import (
    FORBIDDEN_AUTH_KEYS,
    FORBIDDEN_SECRET_PATTERNS,
)


def default_catalog_path() -> pathlib.Path:
    """Get the default catalog file path.
    
    Checks for ORR_CATALOG_PATH environment variable first,
    then falls back to ~/.orr/catalog.yaml.
    
    Returns:
        Path to the catalog file
    """
    env_path = os.environ.get("ORR_CATALOG_PATH")
    if env_path:
        return pathlib.Path(env_path)
    
    home = pathlib.Path.home()
    orr_dir = home / ".orr"
    return orr_dir / "catalog.yaml"


def write_catalog_yaml(
    path: str | pathlib.Path,
    document: Dict[str, Any],
    *,
    check_secrets: bool = True,
    mode: int = 0o600,
) -> None:
    """Write the catalog document to a YAML file.
    
    This function:
    - Creates parent directories if they don't exist
    - Writes the YAML with proper formatting
    - Sets file permissions to 0600 (owner read/write only)
    - Optionally scans for secrets before writing
    
    Args:
        path: File path (string or Path)
        document: The catalog document to write
        check_secrets: Whether to scan for secrets before writing
        mode: File mode to set (default: 0o600)
        
    Raises:
        ValueError: If secrets are detected and check_secrets is True
        OSError: If file write fails
    """
    path = pathlib.Path(path)
    
    # Create parent directories
    parent_dir = path.parent
    if not parent_dir.exists():
        parent_dir.mkdir(parents=True, mode=0o700)
    
    # Ensure parent directory has secure permissions
    try:
        os.chmod(parent_dir, 0o700)
    except OSError:
        # On some systems (e.g., Windows), chmod may not work as expected
        pass
    
    # Scan for secrets if requested
    if check_secrets:
        secrets_found = _scan_document_for_secrets(document)
        if secrets_found:
            raise ValueError(
                f"Refusing to write catalog with potential secrets: {secrets_found}"
            )
    
    # Write YAML
    yaml_str = yaml.dump(
        document,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    
    # Write file temporarily first, then move to final location
    temp_path = path.with_suffix(".tmp")
    try:
        temp_path.write_text(yaml_str, encoding="utf-8")
        # Set permissions on temp file
        try:
            os.chmod(temp_path, mode)
        except OSError:
            pass
        
        # Atomic rename
        temp_path.replace(path)
        
        # Ensure final permissions (rename may not preserve them)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
            
    finally:
        # Clean up temp file if it still exists
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _scan_document_for_secrets(document: Dict[str, Any]) -> list:
    """Scan document for forbidden secrets.
    
    Args:
        document: The catalog document to scan
        
    Returns:
        List of error messages describing found secrets
    """
    errors = []
    _scan_for_secrets_recursive(document, "", errors)
    return errors


def _scan_for_secrets_recursive(
    data: Any,
    path: str,
    errors: list,
) -> None:
    """Recursively scan for secrets in data.
    
    Args:
        data: The data to scan
        path: Current path in the data structure
        errors: List to append error messages to
    """
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}.{key}" if path else key
            
            # Check for forbidden auth keys
            if key.lower() in {k.lower() for k in FORBIDDEN_AUTH_KEYS}:
                errors.append(f"Forbidden auth key '{key}' at {new_path}")
            
            # Check string values for secret patterns
            if isinstance(value, str):
                for pattern in FORBIDDEN_SECRET_PATTERNS:
                    if value.startswith(pattern):
                        errors.append(
                            f"Potential secret value (starts '{pattern}') at {new_path}"
                        )
            
            # Recurse
            _scan_for_secrets_recursive(value, new_path, errors)
            
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}[{i}]" if path else f"[{i}]"
            _scan_for_secrets_recursive(item, new_path, errors)
            
    elif isinstance(data, str):
        for pattern in FORBIDDEN_SECRET_PATTERNS:
            if data.startswith(pattern):
                errors.append(
                    f"Potential secret value (starts '{pattern}') at {path}"
                )
