# mcp-mistral-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

Un serveur MCP (Model Context Protocol) et outil CLI qui coordonne les appels locaux, multi-processus et multi-clients vers le niveau gratuit de Mistral (environ 1 requête / 30 secondes) via une file d'attente SQLite partagée.
Il utilise SQLite (mode WAL) et une file d'attente asynchrone avec une seule tâche en cours pour espacer les démarrages de requête. Il s'agit d'un contrôle de trafic de type "best effort", et non d'un SLA officiel.

## Fonctionnalités

 * **Coordination automatique des limites de débit** : intervalle de départ partagé d'environ 31 secondes ; en cas de 429, repli partagé puis réentrée dans la porte. Réinitialisation à l'intervalle de base en cas de succès.
 * **Multi-processus et contrôle de priorité** : plusieurs processus/tâches peuvent mettre des travaux en file. Priorité (1-3) plus traitement séquentiel avec une seule tâche en cours pour ordonner la file.
 * **Options flexibles de modèle et de message** : n'importe quel nom de modèle de chat Mistral (par défaut `mistral-small-latest` ; par exemple `mistral-large-latest`, `codestral-latest`), ainsi que l'historique complet de conversation via un tableau `messages`.
 * **Streaming et gestion de l'annulation** : diffusion interne de la réponse de l'API Mistral (l'outil retourne le texte complet) ; en cas d'annulation client (`CancelledError`), mise à jour du statut de la tâche dans la base de données.
 * **Base de données de contrôle locale** : base de données temporaire dans un répertoire par utilisateur avec le mode `0700` (chemin remplaçable via `MMQ_TEMP_DB_PATH`).
 * **Compatible uv** : métadonnées de script en ligne PEP 723 ; utilisez `uv run` pour résoudre les dépendances.
 * **Intégration Mistral Vibe** : enregistrez en tant que serveur MCP (`--mcp`) pour Vibe / Claude Desktop / clients similaires. Utilisation CLI directe via `uv run` (pas via `vibe mmq.py ...`).

## Prérequis

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) installé (0.1.0+ recommandé)
 * Une clé API Mistral (`MISTRAL_API_KEY`)

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```

## Utilisation

### 1. Mode CLI (exécution directe)

**Exécutez le script avec `uv run`.**
La commande `vibe` est le **CLI agent** de Mistral Vibe ; `vibe mmq.py "..."` n'exécute **pas** ce script.

```bash
# Exécution de base (modèle par défaut : mistral-small-latest)
uv run mmq.py "Explain Python list comprehensions briefly"

# Choix d'un modèle (par exemple mistral-large-latest, codestral-latest)
uv run mmq.py -m mistral-large-latest "Explain a complex algorithm"

# Invite système personnalisée
uv run mmq.py -s "You are an AI that speaks casually." "How is the weather today?"

# Priorité (1 : haute, 2 : normale, 3 : basse)
uv run mmq.py --priority 1 "Urgent question"

# Contexte de conversation complet sous forme de tableau JSON de messages
uv run mmq.py --messages '[{"role":"system","content":"Strict programmer"},{"role":"user","content":"What is ownership in Rust?"}]'
```

### 2. Mode serveur MCP (Mistral Vibe / autres clients)

Exposez l'outil **`ask_mistral`** à Vibe, Claude Desktop, OpenCode, Goose et clients similaires.
Ceci est un chemin distinct du CLI `uv run mmq.py "..."`.

Utilisez un **chemin absolu** vers le fichier `mmq.py` de ce dépôt (le package n'est pas encore sur PyPI).
`uv run` résout les dépendances PEP 723 ; voir [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

**Exemple pour Vibe / Claude Desktop** (`claude_desktop_config.json` ou équivalent) :

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

Après avoir modifié la configuration, redémarrez le client et faites utiliser l'outil `ask_mistral` par l'agent (passez `model` si nécessaire, par exemple `mistral-large-latest`).

> **Après une publication PyPI :** `uvx` / l'installation publiée peut remplacer la forme par chemin. Le script console est `mmq` (voir `pyproject.toml`), et non `mcp-mistral-queue`. Suivi dans [docs/tasks.md](docs/tasks.md).

### Outils MCP

Lorsque le serveur est en cours d'exécution, les clients peuvent utiliser les outils suivants :

#### `ask_mistral`

| Argument | Type | Défaut | Description |
|---|---|---|---|
| prompt | string | null | Texte d'invite utilisateur en une seule fois |
| messages | array | null | Historique de conversation (`[{"role": "...", "content": "..."}]`) |
| model | string | `"mistral-small-latest"` | Nom du modèle Mistral |
| system_prompt | string | null | Invite système personnalisée (uniquement lors de l'utilisation de `prompt`) |
| priority | number | 2 | Priorité de la tâche (1 : haute, 2 : normale, 3 : basse) |

## Emplacement des données de contrôle

La base de données temporaire de coordination est stockée dans un répertoire par utilisateur créé avec le mode `0700` :

 * Par défaut : `<tempdir>/mcp_mistral_queue_<USER>/mcp_mistral_flow_control.db`
   (`tempfile.gettempdir()`, souvent `/tmp` sous Linux)
 * Remplacement : définissez `MMQ_TEMP_DB_PATH` avec un chemin de fichier complet (le répertoire parent est créé avec `0700`)

## Tests

```bash
# Unitaires + e2e (API factice ; aucun réseau requis)
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/ -v -m "not live"

# e2e uniquement
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e -v -m "not live"

# API réelle (optionnelle ; consomme le quota du niveau gratuit)
export MISTRAL_API_KEY=...
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_live_api.py -v -m live
```

e2e utilise `MMQ_FAKE_API=1` et un `MMQ_BASE_WAIT_TIME` court pour tester les limites de processus (CLI / MCP stdio).
Pour une vérification manuelle de l'interface Vibe, voir [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

## Licence

MIT License

Copyright (c) 2026 utenadev
