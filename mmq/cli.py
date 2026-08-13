# mmq/cli.py
"""mmq command-line interface (subcommand-based)."""

import argparse
import sys
import os
import logging
from typing import Optional

from . import __version__  # Assuming __version__ is defined in __init__.py
from .config import DEFAULT_MODEL
from .db import (
    register_task as db_register_task,
    purge_tasks as db_purge_tasks,
)
from .mcp_server import start_mcp_server, start_mcp_server_stdio, _MCP_ENABLED
from .catalog.fetch import fetch_catalog
from .catalog.write import write_catalog_yaml

logger = logging.getLogger("mistral-managed-queue")

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmq",
        description="Mistral API queue management tool (subcommand-based)",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Start the MCP server on stdio (legacy flag, equivalent to the 'mcp' command)",
    )
    subparsers = parser.add_subparsers(dest="command", help="available commands")

    # ---- ask / fetch (prompt-based flows) ----
    ask_parser = subparsers.add_parser(
        "ask", help="Send a prompt directly and get an immediate reply (bypasses the queue)"
    )
    ask_parser.add_argument("prompt", nargs="+", help="prompt to send")
    ask_parser.add_argument("-m", "--model", help="model name to use")
    ask_parser.add_argument("-s", "--system-prompt", help="system prompt")
    ask_parser.add_argument(
        "-j", "--json", action="store_true", help="output the result as JSON"
    )

    # ---- fetch: enqueue a prompt for later processing ----
    fetch_parser = subparsers.add_parser(
        "fetch", help="Enqueue a prompt to be processed by `mmq work`"
    )
    fetch_parser.add_argument("prompt", nargs="+", help="prompt to enqueue")
    fetch_parser.add_argument("-m", "--model", help="model name to use")
    fetch_parser.add_argument("-s", "--system-prompt", help="system prompt")
    fetch_parser.add_argument(
        "-p", "--priority", type=int, default=2, help="priority (larger value is processed first)"
    )

    # ---- work: process the queue (worker mode) ----
    work_parser = subparsers.add_parser(
        "work", help="Process pending tasks (highest priority first)"
    )
    work_group = work_parser.add_mutually_exclusive_group()
    work_group.add_argument(
        "--once",
        action="store_true",
        help="process only one task and exit",
    )
    work_group.add_argument(
        "--watch",
        action="store_true",
        help="keep processing new tasks until interrupted",
    )

    # ---- purge (replaces legacy flags) ----
    purge_parser = subparsers.add_parser(
        "purge", help="Delete tasks from the queue"
    )
    purge_group = purge_parser.add_mutually_exclusive_group(required=True)
    purge_group.add_argument(
        "--pending", action="store_true", help="delete only tasks with status 'pending'"
    )
    purge_group.add_argument(
        "--all", action="store_true", help="delete all tasks (dangerous; for tests etc.)"
    )
    purge_group.add_argument(
        "--id", type=int, help="delete only the task with this ID"
    )

    # ---- catalog (new feature) ----
    catalog_parser = subparsers.add_parser(
        "catalog", help="Fetch and display provider model catalogs"
    )
    catalog_sub = catalog_parser.add_subparsers(dest="subcommand", required=True)
    catalog_fetch = catalog_sub.add_parser(
        "fetch", help="Fetch model lists from available providers and write YAML"
    )
    catalog_fetch.add_argument(
        "-o", "--output", default="models.yaml", help="output file name (default: models.yaml)"
    )
    catalog_fetch.add_argument(
        "--no-validate", action="store_true", help="skip validation of the fetched result"
    )

    # ---- MCP (only shown when enabled) ----
    if _MCP_ENABLED:
        mcp_parser = subparsers.add_parser(
            "mcp", help="MCP server operations (only available when MMQ_ENABLE_MCP is true)"
        )
        mcp_sub = mcp_parser.add_subparsers(dest="subcommand", required=True)
        run_parser = mcp_sub.add_parser(
            "run", help="Start the MCP server (host/port via env vars or arguments)"
        )
        run_parser.add_argument("--host", default="127.0.0.1")
        run_parser.add_argument("--port", type=int, default=8000)
        mcp_sub.add_parser(
            "status", help="Show MCP server availability"
        )

    return parser

def _resolve_args(args: argparse.Namespace) -> int:
    """Dispatch per-subcommand handling and return the exit code."""
    if args.command == "ask":
        # Direct Mistral API call (immediate reply, no queue)
        from .core import call_mistral_api, MistralRequest
        import os
        import asyncio
        prompt = " ".join(args.prompt)
        req = MistralRequest(
            prompt=prompt,
            model=args.model or DEFAULT_MODEL,
            system_prompt=args.system_prompt,
        )
        result = asyncio.run(call_mistral_api(
            api_key=os.environ.get("MISTRAL_API_KEY", ""),
            model=req.model,
            messages=req.to_messages(),
        ))
        if args.json:
            import json
            print(json.dumps({"response": result}, ensure_ascii=False, indent=2))
        else:
            print(result)
        return 0

    if args.command == "fetch":
        # Enqueue and exit (`mmq work` processes it later)
        prompt = " ".join(args.prompt)
        task_id = db_register_task(
            prompt=prompt,
            model=args.model,
            system_prompt=args.system_prompt,
            priority=args.priority,
        )
        print(f"Task enqueued. ID: {task_id}")
        print(f"Run `mmq work` to process it.")
        return 0

    if args.command == "work":
        from .core import (
            drain_queue_async,
            execute_next_task_async,
            watch_queue_async,
        )
        import asyncio
        if args.once:
            result = asyncio.run(execute_next_task_async())
            print("Processed 1 task." if result is not None else "No pending tasks.")
            return 0
        if args.watch:
            asyncio.run(watch_queue_async())
            return 0
        count = asyncio.run(drain_queue_async())
        print(f"Processed {count} task(s).")
        return 0

    if args.command == "purge":
        if args.pending:
            n = db_purge_tasks(pending=True, all=False, task_id=None)
            print(f"Deleted {n} pending task(s).")
        elif args.all:
            n = db_purge_tasks(pending=False, all=True, task_id=None)
            print(f"Deleted all {n} task(s). (Note: this operation cannot be undone)")
        elif args.id is not None:
            n = db_purge_tasks(pending=False, all=False, task_id=args.id)
            print(f"Deleted task with ID {args.id}.")
        else:
            # Should never reach here (required=True)
            parser = _build_parser()
            parser.error("purge requires one of --pending / --all / --id")
        return 0

    if args.command == "catalog":
        if args.subcommand == "fetch":
            catalog = fetch_catalog(use_rate_gate=False, validate=not args.no_validate)
            write_catalog_yaml(args.output, catalog.document)
            print(f"Catalog written to {args.output}.")
            return 0
        # Future catalog subcommands (e.g. list) could be added here
        parser = _build_parser()
        parser.error(f"Unknown catalog subcommand: {args.subcommand}")
        return 1

    if args.command == "mcp":
        if not _MCP_ENABLED:
            logger.error("MCP is disabled. Set MMQ_ENABLE_MCP=true to enable it.")
            return 1
        if args.subcommand == "run":
            start_mcp_server(host=args.host, port=args.port)
            return 0
        if args.subcommand == "status":
            # Simple availability check (actual socket checks could be added)
            from .mcp_server import mcp
            if mcp is not None:
                print("MCP server is enabled (check separately whether it is running)")
            else:
                print("MCP server is disabled")
            return 0
        parser = _build_parser()
        parser.error(f"Unknown mcp subcommand: {args.subcommand}")
        return 1

    # Should not normally reach here
    logger.error("Unknown command: %s", args.command)
    return 1

def main(argv: Optional[list[str]] = None) -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "mcp", False):
        start_mcp_server_stdio()
        sys.exit(0)
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    sys.exit(_resolve_args(args))

# Backward-compatible wrapper so the legacy `mmq:main` entry still works
# (pyproject.toml [project.scripts] points here)
def run_cli() -> None:  # pragma: no cover
    main()

if __name__ == "__main__":
    main()