"""Tests for mmq.catalog.validate module.

This follows t_wada style TDD: test validation before full implementation.
"""

import pytest

from mmq.catalog.validate import validate_catalog


class TestValidateCatalog:
    """Test catalog validation."""

    def test_empty_document_missing_required_fields(self):
        """Empty document should fail validation."""
        errors = validate_catalog({})
        assert len(errors) > 0
        assert any("schema_version" in e for e in errors)

    def test_minimal_valid_document(self):
        """Minimal valid document should pass validation."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_minimal_valid_document_with_providers(self):
        """Document with empty providers list should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_wrong_schema_version(self):
        """Wrong schema version should fail."""
        doc = {
            "schema_version": 2,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("schema_version" in e and "2" in e for e in errors)

    def test_missing_generated_at(self):
        """Missing generated_at should fail."""
        doc = {
            "schema_version": 1,
            "providers": [],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("generated_at" in e for e in errors)

    def test_missing_providers(self):
        """Missing providers should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("providers" in e for e in errors)

    def test_providers_not_a_list(self):
        """Providers as non-list should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": "not a list",
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("providers" in e and "list" in e for e in errors)

    def test_valid_document_with_generator(self):
        """Document with generator field should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "generator": "fetch_orr_catalog.py+mmq-0.1.2",
            "providers": [],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0


class TestValidateProviders:
    """Test provider validation."""

    def test_empty_providers_list(self):
        """Empty providers list should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_provider_missing_id(self):
        """Provider without id should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("id" in e for e in errors)

    def test_provider_minimal_valid(self):
        """Minimal valid provider should pass."""
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
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_provider_missing_auth(self):
        """Provider without auth should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("auth" in e for e in errors)

    def test_provider_auth_missing_type(self):
        """Provider auth without type should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"env": "TEST_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("auth" in e and "type" in e for e in errors)

    def test_provider_auth_missing_env(self):
        """Provider auth without env should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("auth" in e and "env" in e for e in errors)

    def test_provider_auth_with_value_key(self):
        """Provider auth with 'value' key should fail."""
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
                        "value": "actual_key_value",
                    },
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("value" in e.lower() for e in errors)

    def test_provider_missing_capabilities(self):
        """Provider without capabilities should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST_KEY"},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("capabilities" in e for e in errors)

    def test_provider_capabilities_missing_keys(self):
        """Provider capabilities missing catalog/chat should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST_KEY"},
                    "capabilities": {},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("catalog" in e or "chat" in e for e in errors)

    def test_provider_missing_models(self):
        """Provider without models should fail."""
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
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("models" in e for e in errors)

    def test_duplicate_provider_ids(self):
        """Duplicate provider IDs should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "openrouter",
                    "display_name": "OpenRouter 1",
                    "base_url": "https://test1.com",
                    "auth": {"type": "bearer_env", "env": "TEST1"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                },
                {
                    "id": "openrouter",
                    "display_name": "OpenRouter 2",
                    "base_url": "https://test2.com",
                    "auth": {"type": "bearer_env", "env": "TEST2"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                },
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("Duplicate provider" in e for e in errors)


class TestValidateModels:
    """Test model validation."""

    def test_model_missing_id(self):
        """Model without id should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [
                        {
                            "price_status": "known",
                        }
                    ],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("id" in e for e in errors)

    def test_model_missing_price_status(self):
        """Model without price_status should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [
                        {
                            "id": "model1",
                        }
                    ],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("price_status" in e for e in errors)

    def test_model_valid_minimal(self):
        """Minimal valid model should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [
                        {
                            "id": "model1",
                            "price_status": "known",
                        }
                    ],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_model_valid_full(self):
        """Full valid model should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [
                        {
                            "id": "model1",
                            "name": "Model 1",
                            "price_status": "free",
                            "prompt_price": 0.0,
                            "completion_price": 0.0,
                            "context_length": 131072,
                            "modality": "text->text",
                            "canonical_slug": "model1",
                            "coding_index": 0.5,
                            "intelligence_index": 0.8,
                            "expiration_date": "2026-12-31",
                            "supported_params": ["temperature", "tools"],
                        }
                    ],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_duplicate_model_ids_within_provider(self):
        """Duplicate model IDs within a provider should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [
                        {
                            "id": "model1",
                            "price_status": "known",
                        },
                        {
                            "id": "model1",
                            "price_status": "free",
                        },
                    ],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("duplicate" in e.lower() for e in errors)

    def test_model_invalid_price_status(self):
        """Model with invalid price_status should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [
                        {
                            "id": "model1",
                            "price_status": "invalid_status",
                        }
                    ],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("price_status" in e and "invalid" in e.lower() for e in errors)

    def test_model_invalid_context_length_type(self):
        """Model with non-numeric context_length should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [
                        {
                            "id": "model1",
                            "price_status": "known",
                            "context_length": "not a number",
                        }
                    ],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("context_length" in e for e in errors)


class TestValidateDefaults:
    """Test defaults validation."""

    def test_defaults_with_valid_provider(self):
        """Defaults with valid provider should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "defaults": {
                "provider_id": "openrouter",
                "model_id": "deepseek/deepseek-chat",
            },
            "providers": [
                {
                    "id": "openrouter",
                    "display_name": "OpenRouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_defaults_with_invalid_provider(self):
        """Defaults with non-existent provider should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "defaults": {
                "provider_id": "nonexistent",
                "model_id": "model1",
            },
            "providers": [
                {
                    "id": "openrouter",
                    "display_name": "OpenRouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("provider_id" in e and "not found" in e for e in errors)

    def test_defaults_missing_model_id_is_ok(self):
        """Defaults without model_id should be OK."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "defaults": {
                "provider_id": "openrouter",
            },
            "providers": [
                {
                    "id": "openrouter",
                    "display_name": "OpenRouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0


class TestValidateSource:
    """Test source validation."""

    def test_source_with_all_fields(self):
        """Source with all fields should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                    "source": {
                        "list_endpoint": "/models",
                        "fetched_at": "2026-08-09T03:14:50Z",
                        "warnings": ["some warning"],
                        "error": None,
                    },
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_source_with_error(self):
        """Source with error field should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                    "source": {
                        "list_endpoint": "/models",
                        "fetched_at": "2026-08-09T03:14:50Z",
                        "warnings": [],
                        "error": "Failed to fetch",
                    },
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0


class TestValidateExtraHeaders:
    """Test extra_headers validation."""

    def test_extra_headers_with_valid_headers(self):
        """Extra headers with valid headers should pass."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "openrouter",
                    "display_name": "OpenRouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "auth": {"type": "bearer_env", "env": "OPENROUTER_API_KEY"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                    "extra_headers": {
                        "HTTP-Referer": "https://github.com/utenadev/orr",
                        "X-Title": "orr",
                    },
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) == 0

    def test_extra_headers_with_authorization(self):
        """Extra headers with Authorization should fail."""
        doc = {
            "schema_version": 1,
            "generated_at": "2026-08-09T03:15:00Z",
            "providers": [
                {
                    "id": "test",
                    "display_name": "Test",
                    "base_url": "https://test.com",
                    "auth": {"type": "bearer_env", "env": "TEST"},
                    "capabilities": {"catalog": True, "chat": True},
                    "models": [],
                    "extra_headers": {
                        "Authorization": "Bearer xyz",
                    },
                }
            ],
        }
        errors = validate_catalog(doc)
        assert len(errors) > 0
        assert any("Authorization" in e or "forbidden" in e.lower() for e in errors)
