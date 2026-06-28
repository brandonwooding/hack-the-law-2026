"""Claude Agent SDK runner for natural-language act ingestion.

One reusable entrypoint, `run_agent`, used by both the CLI script
(scripts/add_act.py) and the FastAPI `/regimes/add` endpoint. The write gate is
centralised in `is_write_command`; the caller decides what happens on a write
via the `confirm` callback (terminal y/n for the CLI; None = autonomous for the
app).
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
)

from .db import load_dotenv

DEFAULT_MODEL = "claude-opus-4-8"


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


#: MCP read/safe tools + built-ins that never need a write prompt.
_ALLOWED_TOOLS = [
    "Read", "Edit", "Glob", "Grep", "WebSearch",
    "mcp__neo4j__get_neo4j_schema",
    "mcp__neo4j__read_neo4j_cypher",
]

SYSTEM_PROMPT = """\
You add a single UK or EU act to a Neo4j legal knowledge graph, end to end.

The repo has a ready pipeline. Use it via Bash — do NOT write fetch/load code.

Steps for every request:
1. Decide jurisdiction: UK or EU.
2. Resolve the stable identifier:
   - UK: legislation id as type/year/number, e.g. ukpga/2023/50. Use WebSearch
     or `curl -s https://www.legislation.gov.uk/...` if you are unsure.
   - EU: the CELEX number, e.g. 32024R1689. Use WebSearch / EUR-Lex if unsure.
   Never guess; verify the identifier before continuing.
3. Plan (fetch only, no graph write):
   `legalgraph ingest --jurisdiction <uk|eu> --id <identifier> --plan`
   Read the JSON: note title, doc_id, provision_count, already_present.
   If already_present is true, say so but you may still proceed.
4. Commit (writes to Neo4j):
   `legalgraph ingest --jurisdiction <uk|eu> --id <identifier> --commit --title "<title>"`
5. Verify with the neo4j tools, e.g. read_neo4j_cypher:
   MATCH (d:Document {id:'<doc_id>'})-[:CONTAINS*]->(p:Provision) RETURN count(p)
6. Finish with a SHORT summary: the act title, identifier, doc_id, and how many
   provisions / edges were added (or why nothing was added).

If you cannot resolve the identifier or the act is not found, stop before any
commit and explain clearly.
"""


def is_write_command(tool_name: str, tool_input: dict) -> bool:
    """True if this tool call writes to the graph (needs the write gate)."""
    if tool_name == "mcp__neo4j__write_neo4j_cypher":
        return True
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if "legalgraph load" in cmd or "legalgraph link" in cmd:
            return True
        if "ingest" in cmd and "--commit" in cmd:
            return True
    return False


#: Out-of-flow operations the agent must NEVER run, even autonomously. The only
#: sanctioned write path is `legalgraph ingest --commit`.
_DESTRUCTIVE_BASH = (
    "detach delete", "drop database", "drop constraint", "drop index",
    "cypher-shell", "rm -rf",
)


def is_destructive_command(tool_name: str, tool_input: dict) -> bool:
    """True for raw destructive DB/system commands outside the ingest flow."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "").lower()
        return any(p in cmd for p in _DESTRUCTIVE_BASH)
    if tool_name == "mcp__neo4j__write_neo4j_cypher":
        q = (tool_input.get("query") or "").lower()
        return "detach delete" in q or "drop " in q or " delete " in q
    return False


def _neo4j_mcp_config() -> dict:
    return {
        "type": "stdio",
        "command": os.environ.get("LEGALGRAPH_UVX", "uvx"),
        "args": ["mcp-neo4j-cypher@0.6.0"],
        "env": {
            k: os.environ[k]
            for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD",
                      "NEO4J_DATABASE")
            if k in os.environ
        },
    }


async def run_agent(
    prompt: str,
    *,
    model: str | None = None,
    confirm: Callable[[str, dict], Awaitable[bool]] | None = None,
) -> str:
    """Run one ingestion request to completion; return the final summary text."""
    load_dotenv()

    async def gate(tool_name, tool_input, context):
        if is_destructive_command(tool_name, tool_input):
            return PermissionResultDeny(
                message="Destructive/out-of-flow command blocked",
                interrupt=True)
        if is_write_command(tool_name, tool_input):
            if confirm is None or await confirm(tool_name, tool_input):
                return PermissionResultAllow()
            return PermissionResultDeny(message="User declined the write",
                                        interrupt=True)
        return PermissionResultAllow()

    options = ClaudeAgentOptions(
        model=model or DEFAULT_MODEL,
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=_ALLOWED_TOOLS,
        disallowed_tools=["Write"],
        cwd=str(_root()),
        mcp_servers={"neo4j": _neo4j_mcp_config()},
        can_use_tool=gate,
        permission_mode="default",
    )

    async def prompts():
        yield {"type": "user",
               "message": {"role": "user", "content": prompt}}

    summary_parts: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.connect(prompts())
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        summary_parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                if not summary_parts and getattr(msg, "result", None):
                    summary_parts.append(msg.result)
    return "\n".join(p for p in summary_parts if p).strip()
