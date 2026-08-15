# Serveur MCP — mistral-managed-queue

Le serveur MCP (Model Context Protocol) expose `ask_mistral` et `get_queue_status`
aux hôtes MCP tels que Vibe, Claude Desktop et Grok.

MCP est **opt-in** : définissez `MMQ_ENABLE_MCP=true` dans l'environnement de l'hôte.

## Contrôle CLI

```bash
MMQ_ENABLE_MCP=true mmq mcp run      # start the MCP server
MMQ_ENABLE_MCP=true mmq mcp status   # show MCP availability
```

## Configuration (PyPI / uvx — recommandé)

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

Si `mmq` est déjà dans le `PATH` (venv / `uv pip install`) :

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

## Checkout local (développement)

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

Après modification de la configuration, redémarrez le client. Liste de contrôle Vibe manuelle : [docs/SMOKE_VIBE.md](../docs/SMOKE_VIBE.md).

## Outils MCP

### `ask_mistral`

| Argument | Type | Défaut | Description |
|---|---|---|---|
| prompt | string | required | Texte de l'invite utilisateur |
| model | string | "mistral-small-latest" | Nom du modèle Mistral |
| system_prompt | string | null | Invite système personnalisée |

### `get_queue_status`

Renvoie l'état actuel de la file partagée au format JSON :

| Champ | Type | Description |
|---|---|---|
| pending | number | Tâches en attente dans la file |
| processing | number | Tâches actuellement revendiquées / en cours |
| completed | number | Tâches terminées |
| failed | number | Tâches en échec |
| total | number | Nombre total de tâches |
| seconds_until_next_slot | number | Secondes avant que la porte de débit n'accorde le prochain créneau |
| current_wait_interval | number | Intervalle d'attente partagé actuel (après repli) |
| in_flight | boolean | Vrai si une tâche est actuellement en cours de traitement |
