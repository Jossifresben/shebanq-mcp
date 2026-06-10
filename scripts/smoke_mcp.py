"""Smoke test against a running shebanq MCP container over streamable-HTTP.

Checks: tools + write-mql prompt are listed; a string query (bara=48) and an
enum query (sp=verb=73710) return the right counts; a mutating query is REJECTED
and leaves the data unchanged.

Usage: python scripts/smoke_mcp.py http://localhost:8000/mcp
"""
import re
import sys

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BARA = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"
VERBS = "SELECT ALL OBJECTS WHERE [word sp=verb] GO"
DROP = "DROP DATABASE 'shebanq_etcbc2021' GO"


def _count(result) -> int:
    data = getattr(result, "structuredContent", None)
    if isinstance(data, dict) and "result_count" in data:
        return int(data["result_count"])
    for block in getattr(result, "content", []) or []:
        m = re.search(r'"result_count"\s*:\s*(\d+)', getattr(block, "text", ""))
        if m:
            return int(m.group(1))
    raise AssertionError(f"no result_count in {result!r}")


def _text(result) -> str:
    parts = [getattr(b, "text", "") for b in getattr(result, "content", []) or []]
    data = getattr(result, "structuredContent", None)
    return (str(data) if data else "") + " ".join(parts)


async def _main(url: str) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert {"run_mql", "lookup_feature", "search_bhsa"} <= tools, tools
            prompts = {p.name for p in (await session.list_prompts()).prompts}
            assert "write_mql" in prompts, prompts

            assert _count(await session.call_tool("run_mql", {"mql": BARA})) == 48
            assert _count(await session.call_tool("run_mql", {"mql": VERBS})) == 73710

            # Mutation must be refused by validation, not executed.
            drop = await session.call_tool("run_mql", {"mql": DROP})
            assert "read-only" in _text(drop) or "mutating" in _text(drop), _text(drop)
            # And the data is still intact afterwards.
            assert _count(await session.call_tool("run_mql", {"mql": BARA})) == 48

            print("SMOKE OK: bara=48, verbs=73710, mutation rejected, data intact")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
    anyio.run(_main, url)
