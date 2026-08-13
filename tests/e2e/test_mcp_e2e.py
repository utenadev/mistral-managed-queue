"""MCP stdio e2e: real FastMCP server process + MCP client session."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_mcp_list_and_call_ask_mistral(
    python_exe, mmq_script, e2e_env, mcp_available
):
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**e2e_env, "MMQ_FAKE_RESPONSE": "mcp-tool-ok"}
    params = StdioServerParameters(
        command=python_exe,
        args=["-m", str(mmq_script), "--mcp"],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            names = [t.name for t in listed.tools]
            assert "ask_mistral" in names
            assert "get_queue_status" in names

            result = await session.call_tool(
                "ask_mistral",
                {"prompt": "hello from mcp e2e"},
            )
            # CallToolResult: content is list of text content blocks
            texts = []
            for block in result.content:
                text = getattr(block, "text", None)
                if text is not None:
                    texts.append(text)
            joined = "\n".join(texts)
            assert "mcp-tool-ok" in joined, f"unexpected tool result: {result!r}"
            assert result.isError is not True


@pytest.mark.asyncio
async def test_mcp_missing_prompt_and_messages_errors(
    python_exe, mmq_script, e2e_env, mcp_available
):
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=python_exe,
        args=["-m", str(mmq_script), "--mcp"],
        env=e2e_env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("ask_mistral", {})
            # FastMCP may surface as isError or text containing the ValueError
            texts = [
                getattr(b, "text", "") or ""
                for b in result.content
            ]
            joined = "\n".join(texts).lower()
            assert result.isError or "prompt" in joined or "messages" in joined


@pytest.mark.asyncio
async def test_mcp_server_starts_and_pings(
    python_exe, mmq_script, e2e_env, mcp_available
):
    """Regression for Issue 6: process must speak MCP (not AttributeError on start)."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=python_exe,
        args=["-m", str(mmq_script), "--mcp"],
        env=e2e_env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init is not None
            # optional capability probe
            await session.send_ping()


@pytest.mark.asyncio
async def test_mcp_get_queue_status(
    python_exe, mmq_script, e2e_env, mcp_available
):
    """get_queue_status is listed and returns a JSON status object."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=python_exe,
        args=["-m", str(mmq_script), "--mcp"],
        env=e2e_env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [t.name for t in listed.tools]
            assert "get_queue_status" in names

            result = await session.call_tool("get_queue_status", {})
            assert result.isError is not True
            texts = [
                getattr(b, "text", "") or ""
                for b in result.content
            ]
            joined = "\n".join(texts)
            data = json.loads(joined)
            for key in (
                "pending",
                "processing",
                "seconds_until_next_slot",
                "current_wait_interval",
                "in_flight",
            ):
                assert key in data, f"missing {key} in {data!r}"
            assert isinstance(data["pending"], int)
            assert isinstance(data["processing"], int)
            assert isinstance(data["in_flight"], bool)


@pytest.mark.asyncio
async def test_mcp_two_concurrent_calls_no_deadlock(
    python_exe, mmq_script, e2e_env, mcp_available
):
    """Two concurrent ask_mistral calls must both complete (regression for H1)."""
    import asyncio

    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**e2e_env, "MMQ_FAKE_RESPONSE": "mcp-conc-ok"}
    params = StdioServerParameters(
        command=python_exe,
        args=["-m", str(mmq_script), "--mcp"],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def _call(prompt):
                res = await session.call_tool("ask_mistral", {"prompt": prompt})
                texts = [
                    getattr(b, "text", "") or ""
                    for b in res.content
                ]
                return "".join(texts)

            results = await asyncio.wait_for(
                asyncio.gather(_call("one"), _call("two")),
                timeout=20,
            )
            assert len(results) == 2
            assert all("mcp-conc-ok" in r for r in results)
