# mistral-managed-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

[![PyPI](https://img.shields.io/pypi/v/mistral-managed-queue)](https://pypi.org/project/mistral-managed-queue/)

Un outil CLI et un serveur MCP (Model Context Protocol) qui coordonne les appels locaux et multi-processus/multi-clients à l'offre gratuite de Mistral (~1 requête / 30 secondes) via une file d'attente partagée SQLite.
Il utilise SQLite (mode WAL) et une file d'attente asynchrone avec une seule tâche en vol pour espacer les débuts de requêtes. Il s'agit d'un contrôle de trafic au mieux, et non d'un SLA officiel.

**Package :** [`mistral-managed-queue`](https://pypi.org/project/mistral-managed-queue/) sur PyPI · **script console :** `mmq` (pas le nom du package) · **version actuelle :** `0.2.0`

## Fonctionnalités

 * **Coordination automatique des limites de débit :** Intervalle de départ partagé d'environ 31 secondes ; en cas de 429, repli partagé puis réintégration de la file. Réinitialisation à l'intervalle de base en cas de succès.
 * **Contrôle multi-processus et de priorité :** Plusieurs processus/tâches peuvent mettre des travaux en file d'attente. La priorité (par défaut 2 ; une valeur plus élevée est traitée en premier) ainsi que l'ordre de traitement de la file (un seul vol en cours) déterminent l'ordre.
 * **Options flexibles de modèle et de message :** N'importe quel nom de modèle de chat Mistral (par défaut `mistral-small-latest` ; par ex. `mistral-large-latest`, `codestral-latest`).
 * **Streaming et gestion des annulations :** Stream la réponse de l'API Mistral en interne (l'outil retourne le texte complet) ; en cas d'annulation côté client (`CancelledError`), met à jour le statut de la tâche dans la base de données.
 * **Base de données de contrôle locale :** Base de données temporaire dans un répertoire par utilisateur avec le mode `0700` (le chemin peut être remplacé via `MMQ_TEMP_DB_PATH`).
 * **PyPI / uvx :** Installation unique ou exécution éphémère ; point d'entrée `mmq`.
 * **Récupération du catalogue :** Récupère et met en cache les catalogues de modèles auprès des fournisseurs (OpenRouter, NVIDIA NIM, Mistral) avec `mmq catalog fetch` (nécessite `pip install mistral-managed-queue[catalog]`).
 * **Adapté à l'offre gratuite :** Tâches occasionnelles (par ex. traduction de documentation) qui peuvent attendre ~31 secondes entre les appels sans épuiser une pile dédiée de limites de débit.

## Prérequis

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) recommandé (`uvx` / `uv run`) ; `pip` fonctionne également
 * Une clé API Mistral (`MISTRAL_API_KEY`)

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```


## Installation (PyPI)

Publié et vérifié sur [PyPI](https://pypi.org/project/mistral-managed-queue/).

```bash
# One-shot (no permanent install) — recommended for MCP hosts
uvx --from mistral-managed-queue mmq --help

# Or install into an environment
uv pip install mistral-managed-queue
# pip install mistral-managed-queue

mmq --help
```


**Test rapide (nécessite `MISTRAL_API_KEY` ; compte dans le quota de l'offre gratuite) :**

```bash
uvx --from mistral-managed-queue mmq ask "Reply with pong only."
```


**Remarques :**

 * Le nom du script console est **`mmq`**. Incorrect : `uvx mistral-managed-queue ...`. Correct : `uvx --from mistral-managed-queue mmq ...`.
 * Dépendances de base : `mcp[cli]>=1.0.0,<2`, `mistralai>=1.0.0,<2`. La récupération du catalogue nécessite `httpx` et `PyYAML` (`pip install mistral-managed-queue[catalog]`).

## Utilisation

Le CLI est basé sur des sous-commandes : `mmq ask`, `mmq fetch`, `mmq work`, `mmq purge`, `mmq catalog`, `mmq mcp`.

### 1. `ask` — appel API direct (contourne la file d'attente)

Envoie l'invite à l'API Mistral immédiatement et affiche la réponse.

```bash
# Basic run (default model: mistral-small-latest)
uvx --from mistral-managed-queue mmq ask "Explain Python list comprehensions briefly"
# or: mmq ask "Explain Python list comprehensions briefly"

# Choose a model (e.g. mistral-large-latest, codestral-latest)
mmq ask -m mistral-large-latest "Explain a complex algorithm"

# Custom system prompt
mmq ask -s "You are an AI that speaks casually." "How is the weather today?"

# JSON output for easy parsing
mmq ask -j "What is ownership in Rust?"
```


### 2. `fetch` — mise en file d'attente pour un traitement asynchrone

Enregistre l'invite dans la file d'attente partagée. Elle **n'est pas** traitée ici — exécutez
`mmq work`
pour vider la file.

```bash
# Enqueue with default priority (2)
mmq fetch "Summarize this document"

# Choose a model / system prompt / priority
mmq fetch -m mistral-large-latest -s "Be concise" -p 1 "Translate this to Japanese"
```


**Priorité :** une valeur plus élevée est traitée en premier (`ORDER BY priority DESC`). La valeur par défaut est `2`.

### 3. `work` — traitement de la file (mode worker)

Réclame et traite les tâches en attente par ordre de priorité (du plus élevé au plus bas ; FIFO pour la même priorité), chacune passant par la porte de débit partagée.

```bash
mmq work            # drain all currently pending tasks
mmq work --once     # process exactly one task and exit
mmq work --watch    # keep processing new tasks until interrupted (Ctrl-C)
```


### 4. `purge` — annulation des tâches en file d'attente

```bash
mmq purge --pending   # delete all pending tasks
mmq purge --all       # delete every task (including completed/failed)
mmq purge --id 42     # delete a specific task by ID
```


### 5. `catalog fetch` — récupération des catalogues de modèles des fournisseurs

Récupère et met en cache les catalogues de modèles auprès des fournisseurs (OpenRouter, NVIDIA NIM, Mistral). Nécessite `pip install mistral-managed-queue[catalog]`).

```bash
# Fetch from all enabled providers and write to ./models.yaml (default)
mmq catalog fetch

# Specify output file
mmq catalog fetch -o ./my-catalog.yaml

# Skip validation
mmq catalog fetch --no-validate
```


La récupération du catalogue utilise sa propre limitation de débit, réglée indépendamment de l'API de chat via `MMQ_CATALOG_BASE_WAIT_TIME` et `MMQ_CATALOG_MAX_WAIT_TIME`. Si non définis, ils reviennent à `MMQ_BASE_WAIT_TIME` / `MMQ_MAX_WAIT_TIME`.

### 6. `mcp` — contrôle du serveur MCP

Uniquement disponible lorsque le MCP est activé (définir `MMQ_ENABLE_MCP=true`).

```bash
MMQ_ENABLE_MCP=true mmq mcp run      # start the MCP server
MMQ_ENABLE_MCP=true mmq mcp status   # show MCP availability
```


### 7. Mode serveur MCP (Vibe / Grok / Claude Desktop / …)

Expose **`ask_mistral`** et **`get_queue_status`** aux hôtes MCP.

Le MCP est **optionnel :** définissez `MMQ_ENABLE_MCP=true` (valeurs : `1` / `true` / `yes` / `on`) dans l'environnement de l'hôte, puis exécutez `mmq mcp run`.

#### PyPI / uvx (recommandé)

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "uvx",
      "args": ["--from", "mistral-managed-queue", "mmq", "mcp", "run"],
      "env": {
        "MMQ_ENABLE_MCP": "true",
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
    "mistral-managed-queue": {
      "command": "mmq",
      "args": ["mcp", "run"],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```


#### Vérification locale (développement)

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]>=1.0.0,<2",
        "--with", "mistralai>=1.0.0,<2",
        "--no-project",
        "python", "-m", "mmq.cli", "mcp", "run"
      ],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```


Après avoir modifié la configuration, redémarrez le client. Liste de vérification manuelle Vibe : [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

### 3. Variables d'environnement (optionnelles)

| Variable | Valeur par défaut | Objectif |
|---|---|---|
| `MISTRAL_API_KEY` | (requis) | Clé API Mistral |
| `MMQ_TEMP_DB_PATH` | par utilisateur dans tempdir | Chemin du fichier de la base de données de la file d'attente partagée |
| `MMQ_BASE_WAIT_TIME` | `31` | Secondes entre les départs (rythme de l'offre gratuite) |
| `MMQ_MAX_WAIT_TIME` | `300` | Temps d'attente maximal de repli |
| `MMQ_MIN_SLEEP_INTERVAL` | `2` | Temps de sommeil minimal entre les tentatives |
| `MMQ_BACKOFF_MULTIPLIER` | `2.0` | Multiplicateur de repli en cas de 429 |
| `MMQ_PROCESSING_TIMEOUT` | `120` | Délai d'expiration des tâches zombies (secondes) |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | Nom du modèle par défaut |
| `MMQ_ENABLE_MCP` | désactivé | Activer le serveur MCP / sous-commandes `mcp` (`1`/`true`) |
| `MMQ_CATALOG_BASE_WAIT_TIME` | `MMQ_BASE_WAIT_TIME` | Rythme de récupération du catalogue |
| `MMQ_CATALOG_MAX_WAIT_TIME` | `MMQ_MAX_WAIT_TIME` | Repli maximal de récupération du catalogue |
| `MMQ_FAKE_API` | désactivé | Hors ligne / e2e : client factice (`1`/`true`) |
| `MMQ_FAKE_RESPONSE` | — | Texte de réponse factice fixe (tests) |
| `MMQ_FAKE_FAIL` | — | `429` ou `error` pour simuler une défaillance (tests) |

### Outils MCP

Lorsque le serveur est en cours d'exécution, les clients peuvent utiliser les outils suivants :

#### `ask_mistral`

| Argument | Type | Valeur par défaut | Description |
|---|---|---|---|
| prompt | chaîne de caractères | requis | Texte de l'invite utilisateur |
| model | chaîne de caractères | `"mistral-small-latest"` | Nom du modèle Mistral |
| system_prompt | chaîne de caractères | null | Invite système personnalisée |

#### `get_queue_status`

Retourne l'état actuel de la file d'attente partagée au format JSON :

| Champ | Type | Description |
|---|---|---|
| pending | nombre | Tâches en attente dans la file |
| processing | nombre | Tâches actuellement réclamées / en cours d'exécution |
| completed | nombre | Tâches terminées |
| failed | nombre | Tâches échouées |
| total | nombre | Tâches totales |
| seconds_until_next_slot | nombre | Secondes avant que la porte de débit n'accorde le prochain créneau |
| current_wait_interval | nombre | Intervalle d'attente partagé actuel (après repli) |
| in_flight | booléen | Vrai si une tâche est actuellement en cours de traitement |

## Emplacement des données de contrôle

La base de données temporaire de coordination est stockée dans un répertoire par utilisateur créé avec le mode `0700` :

 * Par défaut : `<tempdir>/mistral_managed_queue_<USER>/mistral_managed_flow_control.db`
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


Les tests e2e utilisent `MMQ_FAKE_API=1` et un `MMQ_BASE_WAIT_TIME` court pour exercer les limites de processus (CLI / stdio MCP).
Pour une vérification manuelle de l'interface Vibe, voir [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

## Exemple : utilisation par lots de mmq (`scripts/translate_readme.py`)

En plus du CLI et du serveur MCP, vous pouvez appeler la file d'attente depuis Python. Ce dépôt fournit un petit exemple :

**[`scripts/translate_readme.py`](scripts/translate_readme.py)** — régénère les README localisés à partir de la source anglaise via la **même file d'attente de l'offre gratuite** que `mmq` / `ask_mistral`.

| Idée | Pourquoi cela convient à mmq |
|------|-----------------------------|
| Tâche occasionnelle | Les modifications de documentation sont bien moins fréquentes que le trafic de chat |
| Peut attendre ~31s | ja puis fr prennent chacun un créneau sous contrôle |
| Base de données partagée | Ne contourne pas les autres clients de l'offre gratuite sur la machine |
| API programmatique | Utilise `execute_mistral_queue_async` + `MistralRequest` |


```bash
export MISTRAL_API_KEY=...
# optional: TRANSLATE_MODEL=mistral-small-latest

# From a git checkout (imports the mmq package on PYTHONPATH via the script)
python scripts/translate_readme.py --lang ja    # one language
python scripts/translate_readme.py --dry-run    # preview, no write
```


Ce que fait l'exemple :

1. Protège les blocs de code délimités (FSM ligne) et les `code` en ligne avec des espaces réservés
2. Met en file d'attente une tâche de traduction par langue via **`execute_mistral_queue_async`**
3. Restaure les espaces réservés, corrige le sélecteur de langue, valide (par ex. délimiteurs équilibrés)
4. Écrit les sorties de manière atomique

Utilisez-le comme modèle pour d'autres tâches par lots peu fréquentes (résumés, extraction structurée) qui devraient partager la porte de l'offre gratuite.

## Remerciements

- **sioois** pour le partage d'informations sur l'offre gratuite de l'API Mistral
([lien](https://zenn.dev/sioois/articles/dea773011514b1)).
- **@fujibee** pour avoir fourni des informations sur l'utilisation des files d'attente avec le mode WAL de SQLite (#agmsg).
- **shunsuke_suzuki** pour la méthodologie de développement de CLI adaptée à l'IA
([lien](https://zenn.dev/shunsuke_suzuki/articles/make-cli-ai-friendly)).

Merci à tous !

## Documentation complémentaire

 * [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) — Manuel de fumée Vibe / MCP
 * [docs/SEARCH_POSITIONING.md](docs/SEARCH_POSITIONING.md) — où se situe la recherche web (hors base mmq)
 * [docs/tasks.md](docs/tasks.md) — backlog
 * [docs/NOTES.md](docs/NOTES.md) — notes de conception

## Licence

Licence MIT

Copyright (c) 2026 utenadev
