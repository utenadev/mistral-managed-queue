"""Tests for mmq.catalog.types module.

This follows t_wada style TDD: define types first, then test them.
"""

import pytest

from mmq.catalog.types import (
    SCHEMA_VERSION,
    PROVIDER_OPENROUTER,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_MISTRAL,
    PriceStatus,
    FORBIDDEN_AUTH_KEYS,
    FORBIDDEN_SECRET_PATTERNS,
    VALID_PROVIDER_IDS,
    VALID_PRICE_STATUSES,
    AuthDict,
    CapabilitiesDict,
    SourceDict,
    ModelDict,
    ProviderDict,
    DefaultsDict,
    CatalogDocument,
    ProviderPluginMeta,
)


class TestConstants:
    """Test constant definitions."""

    def test_schema_version_is_1(self):
        """Schema version should be 1."""
        assert SCHEMA_VERSION == 1

    def test_provider_ids_are_strings(self):
        """Provider IDs should be lowercase strings."""
        assert PROVIDER_OPENROUTER == "openrouter"
        assert PROVIDER_NVIDIA_NIM == "nvidia_nim"
        assert PROVIDER_MISTRAL == "mistral"

    def test_valid_provider_ids_set(self):
        """Valid provider IDs set should contain all known providers."""
        assert PROVIDER_OPENROUTER in VALID_PROVIDER_IDS
        assert PROVIDER_NVIDIA_NIM in VALID_PROVIDER_IDS
        assert PROVIDER_MISTRAL in VALID_PROVIDER_IDS

    def test_valid_price_statuses(self):
        """Valid price statuses should include all defined statuses."""
        assert "known" in VALID_PRICE_STATUSES
        assert "free" in VALID_PRICE_STATUSES
        assert "dynamic" in VALID_PRICE_STATUSES
        assert "unknown" in VALID_PRICE_STATUSES

    def test_forbidden_auth_keys(self):
        """Forbidden auth keys should be lowercase."""
        for key in FORBIDDEN_AUTH_KEYS:
            assert key.islower()

    def test_forbidden_secret_patterns(self):
        """Forbidden secret patterns should be common prefix patterns."""
        assert "sk-or-" in FORBIDDEN_SECRET_PATTERNS
        assert "sk-" in FORBIDDEN_SECRET_PATTERNS
        assert "nvapi-" in FORBIDDEN_SECRET_PATTERNS
        # Mistral model IDs legitimately start with "mistral-"; flagging that
        # prefix breaks every fetched catalog (regression: agy+opus review).
        assert "mistral-" not in FORBIDDEN_SECRET_PATTERNS


class TestTypedDicts:
    """Test TypedDict definitions."""

    def test_auth_dict_has_required_keys(self):
        """AuthDict should have type and env."""
        # Create a valid auth dict
        auth: AuthDict = {
            "type": "bearer_env",
            "env": "OPENROUTER_API_KEY",
        }
        assert auth["type"] == "bearer_env"
        assert auth["env"] == "OPENROUTER_API_KEY"

    def test_capabilities_dict_has_required_keys(self):
        """CapabilitiesDict should have catalog and chat."""
        caps: CapabilitiesDict = {
            "catalog": True,
            "chat": True,
        }
        assert caps["catalog"] is True
        assert caps["chat"] is True

    def test_source_dict_optional_fields(self):
        """SourceDict should have optional error and warnings."""
        source: SourceDict = {
            "list_endpoint": "/models",
            "fetched_at": "2026-08-09T03:15:00Z",
            "warnings": [],
            "error": None,
        }
        assert source["list_endpoint"] == "/models"
        assert source["error"] is None

    def test_model_dict_required_fields(self):
        """ModelDict should have id and price_status as required."""
        model: ModelDict = {
            "id": "deepseek/deepseek-chat",
            "price_status": "known",
        }
        assert model["id"] == "deepseek/deepseek-chat"
        assert model["price_status"] == "known"

    def test_model_dict_all_optional_fields(self):
        """ModelDict should accept all optional fields."""
        model: ModelDict = {
            "id": "test/model",
            "price_status": "free",
            "name": "Test Model",
            "context_length": 131072,
            "modality": "text->text",
            "canonical_slug": "test/model",
            "prompt_price": 0.0,
            "completion_price": 0.0,
            "coding_index": 0.5,
            "intelligence_index": 0.8,
            "expiration_date": "2026-12-31",
            "supported_params": ["temperature", "tools"],
            "endpoints_summary": {"provider_count": 3},
        }
        assert model["name"] == "Test Model"
        assert model["context_length"] == 131072

    def test_provider_dict_required_fields(self):
        """ProviderDict should have all required fields."""
        provider: ProviderDict = {
            "id": "openrouter",
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {
                "type": "bearer_env",
                "env": "OPENROUTER_API_KEY",
            },
            "capabilities": {
                "catalog": True,
                "chat": True,
            },
            "models": [],
        }
        assert provider["id"] == "openrouter"
        assert provider["base_url"] == "https://openrouter.ai/api/v1"

    def test_provider_dict_optional_fields(self):
        """ProviderDict should accept optional source and extra_headers."""
        provider: ProviderDict = {
            "id": "openrouter",
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {
                "type": "bearer_env",
                "env": "OPENROUTER_API_KEY",
            },
            "capabilities": {
                "catalog": True,
                "chat": True,
            },
            "models": [],
            "source": {
                "list_endpoint": "/models",
                "fetched_at": "2026-08-09T03:15:00Z",
                "warnings": [],
                "error": None,
            },
            "extra_headers": {
                "HTTP-Referer": "https://github.com/utenadev/orr",
                "X-Title": "orr",
            },
        }
        assert provider["source"]["list_endpoint"] == "/models"
        assert "HTTP-Referer" in provider["extra_headers"]

    def test_defaults_dict(self):
        """DefaultsDict should have optional provider_id and model_id."""
        defaults: DefaultsDict = {
            "provider_id": "openrouter",
            "model_id": "deepseek/deepseek-chat",
        }
        assert defaults["provider_id"] == "openrouter"
        assert defaults["model_id"] == "deepseek/deepseek-chat"

    def test_catalog_document_complete(self):
        """CatalogDocument should have all required fields."""
        doc: CatalogDocument = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [],
        }
        assert doc["schema_version"] == 1
        assert "generated_at" in doc
        assert "providers" in doc

    def test_catalog_document_with_all_fields(self):
        """CatalogDocument should accept all optional fields."""
        doc: CatalogDocument = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "generator": "fetch_orr_catalog.py+mmq-0.1.2",
            "defaults": {
                "provider_id": "openrouter",
                "model_id": "deepseek/deepseek-chat",
            },
            "providers": [],
        }
        assert doc["generator"] == "fetch_orr_catalog.py+mmq-0.1.2"
        assert doc["defaults"]["provider_id"] == "openrouter"

    def test_provider_plugin_meta(self):
        """ProviderPluginMeta should have all required fields."""
        meta: ProviderPluginMeta = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {
                "type": "bearer_env",
                "env": "OPENROUTER_API_KEY",
            },
            "capabilities": {
                "catalog": True,
                "chat": True,
            },
            "extra_headers": None,
        }
        assert meta["display_name"] == "OpenRouter"
        assert meta["extra_headers"] is None
