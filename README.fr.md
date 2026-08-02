# mcp-mistral-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

[![PyPI](https://img.shields.io/pypi/v/mcp-mistral-queue)](https://pypi.org/project/mcp-mistral-queue/)

Un serveur MCP (Model Context Protocol) et un outil CLI qui coordonne les appels locaux et multi-processus/multi-clients à l'offre gratuite de Mistral (~1 requête / 30 secondes) via une file d'attente partagée SQLite.
Il utilise SQLite (mode WAL) et une file d'attente asynchrone avec une seule tâche en vol pour espacer les débuts de requête. Il s'agit d'un contrôle de trafic au mieux, et non d'un SLA officiel.

**Package :** [`mcp-mistral-queue`](https://pypi.org/project/mcp-mistral-queue/) sur PyPI · **script console :** `mmq` (pas le nom du package) · **version actuelle :** `0.1.0`

## Fonctionnalités

 * **Coordination automatique des limites de débit :** Intervalle de début partagé d'environ 31 secondes ; en cas de 429, repli partagé puis réintégration de la file. Réinitialisation à l'intervalle de base en cas de succès.
 * **Contrôle multi-processus et de priorité :** Plusieurs processus/tâches peuvent mettre des travaux en file d'attente. La priorité (1–3) ainsi que l'ordre de traitement de la file d'attente unique déterminent l'ordre de la file.
 * **Options flexibles de modèle et de message :** Tout nom de modèle de chat Mistral (par défaut `mistral-small-latest` ; par ex. `mistral-large-latest`, `codestral-latest`), ainsi que l'historique complet de la conversation via un tableau `messages`.
 * **Streaming et gestion des annulations :** Stream la réponse de l'API Mistral en interne (l'outil retourne le texte complet) ; en cas d'annulation par le client (`CancelledError`), met à jour le statut de la tâche dans la base de données.
 * **Base de données de contrôle locale :** Base de données temporaire dans un répertoire par utilisateur avec le mode `0700` (le chemin peut être remplacé via `MMQ_TEMP_DB_PATH`).
 * **PyPI / uvx :** Installation unique ou exécution éphémère ; le point d'entrée est `mmq`.
 * **Mistral Vibe / Grok / Claude Desktop :** Enregistrement en tant que serveur MCP (`mmq --mcp`). **Ne pas** utiliser `vibe mmq.py "..."` — cela exécute le CLI de l'agent Vibe, pas cet outil.
 * **Adapté à l'offre gratuite :** Tâches occasionnelles (par ex. traduction de documentation) qui peuvent attendre ~31 secondes entre les appels sans épuiser une pile de limites de débit dédiée.

## Prérequis

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) recommandé (`uvx` / `uv run`) ; `pip` fonctionne également
 * Une clé API Mistral (`MISTRAL_API_KEY`)

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```


## Installation (PyPI)

Publié et vérifié sur [PyPI](https://pypi.org/project/mcp-mistral-queue/).

```bash
# One-shot (no permanent install) — recommended for MCP hosts
uvx --from mcp-mistral-queue mmq --help

# Or install into an environment
uv pip install mcp-mistral-queue
# pip install mcp-mistral-queue

mmq --help
```


**Test rapide (nécessite `MISTRAL_API_KEY` ; compte contre le quota de l'offre gratuite) :**

```bash
uvx --from mcp-mistral-queue mmq "Reply with pong only."
```


**Remarques :**

 * Le nom du script console est **`mmq`**. Faux : `uvx mcp-mistral-queue --mcp`. Correct : `uvx --from mcp-mistral-queue mmq --mcp`.
 * Dépendances : `mcp[cli]>=1.0.0,<2`, `mistralai>=1.0.0,<2` (inclus dans le package).

## Utilisation

### 1. Mode CLI

Après installation via PyPI / via `uvx`, invoquez **`mmq`**.
Depuis une copie locale du dépôt, vous pouvez toujours utiliser `uv run mmq.py ...` (PEP 723).

```bash
# Basic run (default model: mistral-small-latest)
uvx --from mcp-mistral-queue mmq "Explain Python list comprehensions briefly"
# or: mmq "Explain Python list comprehensions briefly"

# Choose a model (e.g. mistral-large-latest, codestral-latest)
mmq -m mistral-large-latest "Explain a complex algorithm"

# Custom system prompt
mmq -s "You are an AI that speaks casually." "How is the weather today?"

# Priority (1: high, 2: normal, 3: low)
mmq --priority 1 "Urgent question"

# Full conversation context as a messages JSON array
# (specify either prompt or --messages, not both)
mmq --messages '[{"role":"system","content":"Strict programmer"},{"role":"user","content":"What is ownership in Rust?"}]'

# Emergency brake: cancel queued / stuck work (no API call)
mmq --purge          # cancel all pending
mmq --purge-all      # cancel pending + processing
mmq --purge-id 42    # cancel one task by ID
```


### 2. Mode serveur MCP (Vibe / Grok / Claude Desktop / …)

Expose **`ask_mistral`** et **`get_queue_status`** aux hôtes MCP.
Séparez le chemin des invites CLI.

#### PyPI / uvx (recommandé)

```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "uvx",
      "args": ["--from", "mcp-mistral-queue", "mmq", "--mcp"],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```


Si `mmq` est déjà sur `PATH` (venv / `uv pip install`) :

```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "mmq",
      "args": ["--mcp"],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```


#### Copie locale du dépôt (développement)

```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]>=1.0.0,<2",
        "--with", "mistralai>=1.0.0,<2",
        "--no-project",
        "/absolute/path/to/mmq.py",
        "--mcp"
      ],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```


Après avoir modifié la configuration, redémarrez le client. Liste de contrôle Vibe manuelle : [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

### 3. Variables d'environnement (optionnel)

| Variable | Valeur par défaut | Objectif |
|---|---|---|
| `MISTRAL_API_KEY` | (requis) | Clé API Mistral |
| `MMQ_TEMP_DB_PATH` | par utilisateur dans tempdir | Chemin du fichier de la base de données de la file d'attente partagée |
| `MMQ_BASE_WAIT_TIME` | `31` | Secondes entre les débuts (rythme de l'offre gratuite) |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | Nom du modèle par défaut |
| `MMQ_FAKE_API` | désactivé | Hors ligne / e2e : client factice (`1`/`true`) |

D'autres paramètres (`MMQ_MAX_WAIT_TIME`, `MMQ_MAX_RETRIES`, …) existent pour l'ajustement ; voir `mmq.py`.

### Outils MCP

Lorsque le serveur est en cours d'exécution, les clients peuvent utiliser les outils suivants :

#### `ask_mistral`

| Argument | Type | Valeur par défaut | Description |
|---|---|---|---|
| prompt | chaîne | null | Texte de l'invite utilisateur ponctuelle |
| messages | tableau | null | Historique de la conversation (`[{"role": "...", "content": "..."}]`) |
| model | chaîne | `"mistral-small-latest"` | Nom du modèle Mistral |
| system_prompt | chaîne | null | Invite système personnalisée (uniquement lors de l'utilisation de `prompt`) |
| priority | nombre | 2 | Priorité de la tâche (1 : élevée, 2 : normale, 3 : basse) |

#### `get_queue_status`

Retourne l'état actuel de la file d'attente partagée / des limites de débit au format JSON :

| Champ | Type | Description |
|---|---|---|
| pending | nombre | Tâches en attente dans la file |
| processing | nombre | Tâches actuellement revendiquées / en cours d'exécution |
| seconds_until_next_slot | nombre | Secondes avant l'ouverture de la porte partagée de l'API |
| current_wait_interval | nombre | Intervalle d'attente partagé actif (secondes) |
| in_flight | booléen | Si une tâche est actuellement en cours de traitement |

## Emplacement des données de contrôle

La base de données temporaire de coordination est stockée dans un répertoire par utilisateur créé avec le mode `0700` :

 * Par défaut : `<tempdir>/mcp_mistral_queue_<USER>/mcp_mistral_flow_control.db`
   (`tempfile.gettempdir()`, souvent `/tmp` sur Linux)
 * Remplacement : définissez `MMQ_TEMP_DB_PATH` sur un chemin de fichier complet (le répertoire parent est créé avec `0700`)

## Tests

```bash
# Unit + e2e (fake API; no network required)
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/ -v -m "not live"

# e2e only
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e -v -m "not live"

# Live API (optional; consumes free-tier quota)
export MISTRAL_API_KEY=...
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_live_api.py -v -m live
```


Les tests e2e utilisent `MMQ_FAKE_API=1` et une courte `MMQ_BASE_WAIT_TIME` pour exercer les limites de processus (CLI / stdio MCP).
Pour une vérification manuelle de l'interface Vibe, voir [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

## Exemple : utilisation par lots de mmq (`scripts/translate_readme.py`)

En plus du CLI et du serveur MCP, vous pouvez appeler la file d'attente depuis Python. Ce dépôt inclut un petit exemple :

**[`scripts/translate_readme.py`](scripts/translate_readme.py)** — régénère les README locaux dans différentes langues à partir de la source anglaise via **la même file d'attente de l'offre gratuite** que `mmq` / `ask_mistral`.

| Idée | Pourquoi cela convient à mmq |
|------|-----------------------------|
| Tâche occasionnelle | Les modifications de documentation sont bien moins fréquentes que le trafic de chat |
| Peut attendre ~31s | ja puis fr prennent chacun un créneau réservé |
| Base de données partagée | Ne contourne pas les autres clients de l'offre gratuite sur la machine |
| API programmatique | Utilise `execute_mistral_queue_async` + `MistralRequest` |


```bash
export MISTRAL_API_KEY=...
# optional: TRANSLATE_MODEL=mistral-small-latest

# From a git checkout (imports mmq.py on PYTHONPATH via the script)
python scripts/translate_readme.py --lang ja    # one language
python scripts/translate_readme.py --dry-run    # preview, no write
```


Ce que fait l'exemple :

1. Protège les blocs de code délimités (FSM linéaire) et les `code` en ligne avec des espaces réservés
2. Met en file d'attente une tâche de traduction par langue via **`execute_mistral_queue_async`**
3. Restaure les espaces réservés, corrige le sélecteur de langue, valide (par ex. balises équilibrées)
4. Écrit les sorties de manière atomique

Utilisez-le comme modèle pour d'autres tâches par lots peu fréquentes (résumés, extraction structurée) qui doivent partager la porte de l'offre gratuite.

## Documentation complémentaire

 * [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) — fumée manuelle Vibe / MCP
 * [docs/SEARCH_POSITIONING.md](docs/SEARCH_POSITIONING.md) — où la recherche web doit se situer (hors base mmq)
 * [docs/tasks.md](docs/tasks.md) — backlog
 * [docs/NOTES.md](docs/NOTES.md) — notes de conception

## Licence

MIT License

Copyright (c) 2026 utenadev
