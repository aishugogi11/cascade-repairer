"""A minimal filesystem MCP server (stdio transport), scoped to a sandbox dir.

Replaces the Node `@modelcontextprotocol/server-filesystem` so no npx/Node is
needed in the container. Built on FastMCP from the `mcp` package (already pulled
in transitively by `openai-agents`).

Run:  python filesystem_server.py <sandbox_root>
The MCP client (MCPServerStdio) launches this as a subprocess and speaks
JSON-RPC over stdin/stdout, so nothing is printed to stdout here.
"""
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Sandbox root: first CLI arg, else cwd. Everything is confined under here.
ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
ROOT.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("filesystem")


def _safe(path: str) -> Path:
    """Resolve `path` and confine it to ROOT (blocks `..` traversal / abs escapes)."""
    p = Path(path)
    p = (p if p.is_absolute() else ROOT / p).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError(f"Path {p} is outside the sandbox {ROOT}")
    return p


@mcp.tool()
def list_directory(path: str = ".") -> list[str]:
    """List file and directory names under a sandbox-relative path."""
    return sorted(os.listdir(_safe(path)))


@mcp.tool()
def read_file(path: str) -> str:
    """Return the UTF-8 text contents of a file."""
    return _safe(path).read_text(encoding="utf-8")


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file with the given text content."""
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {p}"


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
