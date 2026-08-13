"""Tests for mmq.catalog.fetch module.

This follows t_wada style TDD: test fetch logic with mocked providers.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from mmq.catalog.fetch import (
    fetch_catalog,
    FetchResult,
    get_plugin_instance,
    _scan_for_secrets,
    _validate_provider_models,
    _build_source_dict,
    _get_timestamp,
    DEFAULT_PROVIDERS,
    PROVIDER_PLUGIN_MAP,
)
from mmq.catalog.types import (
    PROVIDER_OPENROUTER,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_MISTRAL,
)


class TestFetchCatalog:
    """Test fetch_catalog function."""

    def test_default_providers(self):
        """Default providers should be in expected order."""
        assert PROVIDER_OPENROUTER in DEFAULT_PROVIDERS
        assert PROVIDER_NVIDIA_NIM in DEFAULT_PROVIDERS
        assert PROVIDER_MISTRAL in DEFAULT_PROVIDERS
        # OpenRouter should be first
        assert DEFAULT_PROVIDERS[0] == PROVIDER_OPENROUTER

    def test_provider_plugin_map(self):
        """Provider plugin map should have all default providers."""
        for provider_id in DEFAULT_PROVIDERS:
            assert provider_id in PROVIDER_PLUGIN_MAP

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_empty_providers(self, mock_get_timestamp, mock_plugin_map):
        """Fetch with no providers should return empty document."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # No providers
        mock_plugin_map.get.return_value = None
        
        result = fetch_catalog(providers=[], use_rate_gate=False)
        
        assert isinstance(result, FetchResult)
        assert result.document["schema_version"] == 1
        assert result.document["providers"] == []

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_single_provider_no_models(self, mock_get_timestamp, mock_plugin_map):
        """Fetch with single provider returning no models."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # Create mock plugin
        mock_plugin = MagicMock()
        mock_plugin.provider_id = PROVIDER_OPENROUTER
        mock_plugin.provider_meta.return_value = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
            "capabilities": {"catalog": True, "chat": True},
            "extra_headers": None,
        }
        mock_plugin.list_raw_models.return_value = []
        mock_plugin_class = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin_map.get.return_value = mock_plugin_class
        
        result = fetch_catalog(providers=[PROVIDER_OPENROUTER], use_rate_gate=False)
        
        assert len(result.document["providers"]) == 1
        assert result.document["providers"][0]["id"] == PROVIDER_OPENROUTER
        assert result.document["providers"][0]["models"] == []

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_with_models(self, mock_get_timestamp, mock_plugin_map):
        """Fetch with provider returning models."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # Create mock plugin
        mock_plugin = MagicMock()
        mock_plugin.provider_id = PROVIDER_OPENROUTER
        mock_plugin.provider_meta.return_value = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
            "capabilities": {"catalog": True, "chat": True},
            "extra_headers": {"HTTP-Referer": "https://github.com/utenadev/orr"},
        }
        mock_plugin.list_raw_models.return_value = [
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat", "pricing": {"prompt": 0, "completion": 0}},
        ]
        mock_plugin.normalize_model.return_value = {
            "id": "deepseek/deepseek-chat",
            "name": "DeepSeek Chat",
            "price_status": "free",
            "prompt_price": 0.0,
            "completion_price": 0.0,
        }
        mock_plugin.is_free.return_value = True
        mock_plugin_class = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin_map.get.return_value = mock_plugin_class
        
        result = fetch_catalog(
            providers=[PROVIDER_OPENROUTER],
            free_only=True,
            use_rate_gate=False,
        )
        
        assert len(result.document["providers"]) == 1
        provider = result.document["providers"][0]
        assert provider["id"] == PROVIDER_OPENROUTER
        assert len(provider["models"]) == 1
        assert provider["models"][0]["id"] == "deepseek/deepseek-chat"
        assert provider["extra_headers"]["HTTP-Referer"] == "https://github.com/utenadev/orr"

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_free_only_filters_paid(self, mock_get_timestamp, mock_plugin_map):
        """Free only mode should filter out paid models."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # Create mock plugin
        mock_plugin = MagicMock()
        mock_plugin.provider_id = PROVIDER_OPENROUTER
        mock_plugin.provider_meta.return_value = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
            "capabilities": {"catalog": True, "chat": True},
            "extra_headers": None,
        }
        
        # Two models: one free, one paid
        raw_models = [
            {"id": "free-model", "name": "Free", "pricing": {"prompt": 0, "completion": 0}},
            {"id": "paid-model", "name": "Paid", "pricing": {"prompt": 0.001, "completion": 0.002}},
        ]
        mock_plugin.list_raw_models.return_value = raw_models
        
        # Return different normalized models
        def normalize_side_effect(raw):
            if raw["id"] == "free-model":
                return {"id": "free-model", "price_status": "free", "prompt_price": 0.0, "completion_price": 0.0}
            else:
                return {"id": "paid-model", "price_status": "known", "prompt_price": 0.001, "completion_price": 0.002}
        
        mock_plugin.normalize_model.side_effect = normalize_side_effect
        
        # free-model is free, paid-model is not
        def is_free_side_effect(normalized, raw):
            return normalized["price_status"] == "free"
        
        mock_plugin.is_free.side_effect = is_free_side_effect
        mock_plugin_class = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin_map.get.return_value = mock_plugin_class
        
        result = fetch_catalog(
            providers=[PROVIDER_OPENROUTER],
            free_only=True,
            use_rate_gate=False,
        )
        
        provider = result.document["providers"][0]
        assert len(provider["models"]) == 1
        assert provider["models"][0]["id"] == "free-model"

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_all_models_includes_paid(self, mock_get_timestamp, mock_plugin_map):
        """All models mode should include paid models."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # Create mock plugin
        mock_plugin = MagicMock()
        mock_plugin.provider_id = PROVIDER_OPENROUTER
        mock_plugin.provider_meta.return_value = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
            "capabilities": {"catalog": True, "chat": True},
            "extra_headers": None,
        }
        
        raw_models = [
            {"id": "free-model", "name": "Free"},
            {"id": "paid-model", "name": "Paid"},
        ]
        mock_plugin.list_raw_models.return_value = raw_models
        mock_plugin.normalize_model.side_effect = lambda raw: {
            "id": raw["id"],
            "price_status": "free" if "free" in raw["id"] else "known",
        }
        mock_plugin.is_free.side_effect = lambda n, r: n["price_status"] == "free"
        mock_plugin_class = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin_map.get.return_value = mock_plugin_class
        
        result = fetch_catalog(
            providers=[PROVIDER_OPENROUTER],
            free_only=False,
            use_rate_gate=False,
        )
        
        provider = result.document["providers"][0]
        assert len(provider["models"]) == 2

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_provider_failure(self, mock_get_timestamp, mock_plugin_map):
        """Provider failure should be recorded in document."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # Create mock plugin that fails
        mock_plugin = MagicMock()
        mock_plugin.provider_id = PROVIDER_OPENROUTER
        mock_plugin.provider_meta.return_value = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
            "capabilities": {"catalog": True, "chat": True},
            "extra_headers": None,
        }
        mock_plugin.list_raw_models.side_effect = Exception("API connection failed")
        mock_plugin_class = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin_map.get.return_value = mock_plugin_class
        
        result = fetch_catalog(
            providers=[PROVIDER_OPENROUTER],
            free_only=True,
            use_rate_gate=False,
        )
        
        assert result.partial is False  # Only one provider, and it failed
        assert len(result.errors) > 0
        assert len(result.document["providers"]) == 1
        provider = result.document["providers"][0]
        assert provider["models"] == []
        assert provider["source"]["error"] == "API connection failed"

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_partial_success(self, mock_get_timestamp, mock_plugin_map):
        """Partial success (some providers succeed, some fail) should be recorded."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        def plugin_map_get(provider_id):
            if provider_id == PROVIDER_OPENROUTER:
                or_plugin = MagicMock()
                or_plugin.provider_id = PROVIDER_OPENROUTER
                or_plugin.provider_meta.return_value = {
                    "display_name": "OpenRouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "extra_headers": None,
                }
                or_plugin.list_raw_models.return_value = []
                or_plugin_class = MagicMock()
                or_plugin_class.return_value = or_plugin
                return or_plugin_class
            elif provider_id == PROVIDER_NVIDIA_NIM:
                nim_plugin = MagicMock()
                nim_plugin.provider_id = PROVIDER_NVIDIA_NIM
                nim_plugin.provider_meta.return_value = {
                    "display_name": "NVIDIA NIM",
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "auth": {"type": "bearer_env", "env": "NVIDIA_API_KEY"},
                    "capabilities": {"catalog": True, "chat": False},
                    "extra_headers": None,
                }
                nim_plugin.list_raw_models.side_effect = Exception("NIM API error")
                nim_plugin_class = MagicMock()
                nim_plugin_class.return_value = nim_plugin
                return nim_plugin_class
            return None
        
        mock_plugin_map.get.side_effect = plugin_map_get
        
        result = fetch_catalog(
            providers=[PROVIDER_OPENROUTER, PROVIDER_NVIDIA_NIM],
            free_only=True,
            use_rate_gate=False,
        )
        
        assert result.partial is True
        assert len(result.errors) > 0
        assert len(result.document["providers"]) == 2

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_defaults_set(self, mock_get_timestamp, mock_plugin_map):
        """Defaults should be set from first provider with models."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # Create mock plugin
        mock_plugin = MagicMock()
        mock_plugin.provider_id = PROVIDER_OPENROUTER
        mock_plugin.provider_meta.return_value = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
            "capabilities": {"catalog": True, "chat": True},
            "extra_headers": None,
        }
        mock_plugin.list_raw_models.return_value = [
            {"id": "first-model", "name": "First"},
        ]
        mock_plugin.normalize_model.return_value = {
            "id": "first-model",
            "price_status": "free",
        }
        mock_plugin.is_free.return_value = True
        mock_plugin_class = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin_map.get.return_value = mock_plugin_class
        
        result = fetch_catalog(
            providers=[PROVIDER_OPENROUTER],
            free_only=True,
            use_rate_gate=False,
        )
        
        defaults = result.document.get("defaults")
        assert defaults is not None
        assert defaults["provider_id"] == PROVIDER_OPENROUTER
        assert defaults["model_id"] == "first-model"

    @patch("mmq.catalog.fetch.PROVIDER_PLUGIN_MAP")
    @patch("mmq.catalog.fetch._get_timestamp")
    def test_fetch_catalog_no_defaults_when_no_models(self, mock_get_timestamp, mock_plugin_map):
        """Defaults should be None when no provider has models."""
        mock_get_timestamp.return_value = "2026-08-09T03:15:00Z"
        
        # Create mock plugin with no models
        mock_plugin = MagicMock()
        mock_plugin.provider_id = PROVIDER_OPENROUTER
        mock_plugin.provider_meta.return_value = {
            "display_name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
            "capabilities": {"catalog": True, "chat": True},
            "extra_headers": None,
        }
        mock_plugin.list_raw_models.return_value = []
        mock_plugin_class = MagicMock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin_map.get.return_value = mock_plugin_class
        
        result = fetch_catalog(
            providers=[PROVIDER_OPENROUTER],
            free_only=True,
            use_rate_gate=False,
        )
        
        defaults = result.document.get("defaults")
        assert defaults is None


class TestSecretScanning:
    """Test secret scanning functions."""

    def test_scan_for_secrets_no_secrets(self):
        """Scanning document with no secrets should return empty list."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = _scan_for_secrets(doc)
        assert len(errors) == 0

    def test_scan_for_secrets_in_auth_value(self):
        """Scanning should detect secrets in auth value."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {
                        "type": "bearer_env",
                        "env": "TEST_KEY",
                        "value": "sk-or-abc123",
                    },
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = _scan_for_secrets(doc)
        assert len(errors) > 0
        assert any("sk-or-" in e for e in errors)

    def test_scan_for_secrets_in_extra_headers(self):
        """Scanning should detect secrets in extra_headers."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                    "extra_headers": {
                        "X-API-Key": "nvapi-abc123",
                    },
                }
            ],
        }
        errors = _scan_for_secrets(doc)
        assert len(errors) > 0
        assert any("nvapi-" in e for e in errors)


class TestBuildSourceDict:
    """Test _build_source_dict function."""

    def test_build_source_dict_minimal(self):
        """Build source dict with minimal info."""
        mock_plugin = MagicMock()
        source = _build_source_dict(
            mock_plugin,
            "/models",
            error=None,
            warnings=None,
        )
        
        assert source["list_endpoint"] == "/models"
        assert "fetched_at" in source
        assert source["warnings"] == []
        assert source["error"] is None

    def test_build_source_dict_with_error(self):
        """Build source dict with error."""
        mock_plugin = MagicMock()
        source = _build_source_dict(
            mock_plugin,
            "/models",
            error="Connection failed",
            warnings=None,
        )
        
        assert source["error"] == "Connection failed"

    def test_build_source_dict_with_warnings(self):
        """Build source dict with warnings."""
        mock_plugin = MagicMock()
        source = _build_source_dict(
            mock_plugin,
            "/models",
            error=None,
            warnings=["warning1", "warning2"],
        )
        
        assert source["warnings"] == ["warning1", "warning2"]


class TestValidateProviderModels:
    """Test _validate_provider_models function."""

    def test_validate_provider_models_empty(self):
        """Empty models list should pass validation."""
        errors = _validate_provider_models("test", [])
        assert len(errors) == 0

    def test_validate_provider_models_valid(self):
        """Valid models should pass validation."""
        models = [
            {"id": "model1", "price_status": "free"},
            {"id": "model2", "price_status": "known"},
        ]
        errors = _validate_provider_models("test", models)
        assert len(errors) == 0

    def test_validate_provider_models_missing_id(self):
        """Model without id should fail."""
        models = [
            {"price_status": "free"},
        ]
        errors = _validate_provider_models("test", models)
        assert len(errors) > 0
        assert any("id" in e for e in errors)

    def test_validate_provider_models_missing_price_status(self):
        """Model without price_status should fail."""
        models = [
            {"id": "model1"},
        ]
        errors = _validate_provider_models("test", models)
        assert len(errors) > 0
        assert any("price_status" in e for e in errors)

    def test_validate_provider_models_duplicate_id(self):
        """Duplicate model IDs should fail."""
        models = [
            {"id": "model1", "price_status": "free"},
            {"id": "model1", "price_status": "known"},
        ]
        errors = _validate_provider_models("test", models)
        assert len(errors) > 0
        assert any("duplicate" in e.lower() for e in errors)
