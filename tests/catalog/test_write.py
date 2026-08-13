"""Tests for mmq.catalog.write.

Covers the secret-scan false-positive regression surfaced by the agy+opus
adversarial review: model IDs that start with "mistral-" must not be treated
as secrets, or `mmq catalog fetch` can never write a Mistral catalog.
"""

from __future__ import annotations

import pathlib

import yaml

from mmq.catalog.write import write_catalog_yaml


def _sample_document() -> dict:
    return {
        "schema_version": 1,
        "generated_at": "2026-08-13T00:00:00Z",
        "generator": "mmq.catalog.fetch_catalog",
        "defaults": {"provider_id": "mistral", "model_id": "mistral-small-latest"},
        "providers": [
            {
                "id": "mistral",
                "display_name": "Mistral",
                "base_url": "https://api.mistral.ai",
                "auth": {"type": "http", "scheme": "Bearer"},
                "capabilities": {"chat": True, "embedding": False},
                "models": [
                    {
                        "id": "mistral-small-latest",
                        "name": "Mistral Small",
                        "status": "public",
                        "price": {"status": "unknown"},
                    },
                    {
                        "id": "mistral-large-latest",
                        "name": "Mistral Large",
                        "status": "public",
                        "price": {"status": "unknown"},
                    },
                ],
                "source": {
                    "list_endpoint": "models",
                    "fetched_at": "2026-08-13T00:00:00Z",
                },
            }
        ],
    }


def test_write_with_mistral_model_ids(tmp_path):
    """Writing a catalog whose model IDs start with 'mistral-' must succeed."""
    out = tmp_path / "catalog.yaml"
    write_catalog_yaml(out, _sample_document())
    assert out.is_file()
    with open(out, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    assert doc["providers"][0]["models"][0]["id"] == "mistral-small-latest"
    assert doc["defaults"]["model_id"] == "mistral-small-latest"


def test_write_still_blocks_real_secret(tmp_path):
    """An actual API-key style value is still refused."""
    out = tmp_path / "catalog.yaml"
    doc = _sample_document()
    doc["providers"][0]["auth"]["value"] = "sk-or-abcdef1234567890"
    try:
        write_catalog_yaml(out, doc)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a real secret pattern")
    assert not out.exists()
