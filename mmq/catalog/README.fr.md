# Catalogue — mistral-managed-queue (extras)

La fonction catalogue récupère les listes de modèles auprès des fournisseurs de LLM
et les écrit au format YAML compatible ORR. Trois fournisseurs sont pris en charge :

- [OpenRouter](https://openrouter.ai)
- [NVIDIA NIM](https://build.nvidia.com/)
- [Mistral AI](https://mistral.ai)

## Installation

Cette fonctionnalité nécessite des dépendances supplémentaires (`httpx` + `PyYAML`) :

```bash
# pip
pip install 'mistral-managed-queue[catalog]'

# uv
uv pip install 'mistral-managed-queue[catalog]'
```

## Utilisation

```bash
# Fetch from all enabled providers and write to ./models.yaml (default)
mmq catalog fetch

# Specify output file
mmq catalog fetch -o ./my-catalog.yaml

# Skip validation
mmq catalog fetch --no-validate
```

La récupération du catalogue utilise sa propre limitation de débit, réglée
indépendamment de l'API de chat via `MMQ_CATALOG_BASE_WAIT_TIME` et
`MMQ_CATALOG_MAX_WAIT_TIME`. Si elles ne sont pas définies, elles retombent
sur `MMQ_BASE_WAIT_TIME` / `MMQ_MAX_WAIT_TIME`.

## Fournisseurs

| Fournisseur | Plugin | Variable de clé API | Liste des modèles |
|---|---|---|---|
| OpenRouter | `OpenRouterPlugin` | `OPENROUTER_API_KEY` | `/api/v1/models` |
| NVIDIA NIM | `NvidiaNimPlugin` | `NVIDIA_API_KEY` | `/v1/models` |
| Mistral | `MistralPlugin` | `MISTRAL_API_KEY` | `/v1/models` |
