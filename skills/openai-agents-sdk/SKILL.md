---
name: openai-agents-sdk
description: OpenAI Agents SDK patterns proven in backend/api/hello.py — plain agents, function tools, and MCP stdio servers. Use when writing or reviewing agent code in this repo.
---

# OpenAI Agents SDK patterns

Every pattern below is working code in `backend/api/hello.py` (package `openai-agents`, imported as `agents`). This repo standardizes on the OpenAI Agents SDK for the LLM layer — not Anthropic.

## Plain agent (no tools)

The minimal shape — see `/agents_no_mcp`:

```python
from agents import Agent, Runner

agent = Agent(
    name="MyAgent",
    model="gpt-4.1-mini",
    instructions="You are a helpful assistant.",
)

# Runner.run is a classmethod — you don't instantiate Runner.
result = await Runner.run(agent, "Hello, Where did the Minnesota Vikings play?", max_turns=10)

# result is a RunResult; return the serializable text.
return {"result": result.final_output}
```

## Function tools

`@function_tool` (or calling `function_tool(fn)`) turns a Python function into a `FunctionTool` — the SDK builds the JSON schema from the signature and docstring. See `/agents_with_function_tool`, which uses a fictitious weather tool (Delano, MN → 60°F):

```python
from agents import Agent, Runner, function_tool

# Keep the plain function separate so tests can call it directly —
# the FunctionTool wrapper is no longer callable as Python.
def _get_weather(city: str) -> str:
    """Get the current weather for a city."""
    if "delano" in city.lower():
        return "The weather in Delano, MN is sunny and 60°F."
    return f"Sorry, I only have weather data for Delano, MN — not {city}."

get_weather = function_tool(_get_weather)

agent = Agent(
    name="Weather Agent",
    model="gpt-4.1-mini",
    instructions="Use the get_weather tool to answer weather questions.",
    tools=[get_weather],
)

result = await Runner.run(agent, "What is the weather in Delano, MN?", max_turns=10)
```

## MCP stdio servers

Tools can also come from an MCP server subprocess via `MCPServerStdio`. **The agent must be created and run *inside* the `async with` block**, while the server subprocess is connected — see `/agents` and `/agents_with_mcp_filesystem`:

```python
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

# mcp-server-fetch is a Python package, so run it in-process with the
# container's own interpreter — no uvx/uv/npx needed.
fetch_server_params = {"command": "python", "args": ["-m", "mcp_server_fetch"]}

async with MCPServerStdio(name="Fetch Server", params=fetch_server_params,
                          client_session_timeout_seconds=60) as server:
    agent = Agent(
        name="MyAgent",
        model="gpt-4.1-mini",
        instructions=PROMPT,
        mcp_servers=[server],
    )
    result = await Runner.run(agent, "What is https://example.com about?", max_turns=10)
```

The repo also ships its own Python filesystem MCP server (`backend/mcp_servers/filesystem_server.py` — no Node/npx needed). Launch it with absolute paths so it resolves regardless of the subprocess cwd:

```python
filesystem_server_params = {
    "command": "python",
    "args": ["/abs/path/to/backend/mcp_servers/filesystem_server.py", SANDBOX_DIR],
}
```

## Gotchas

- `Runner.run` is a classmethod; never `Runner()`.
- Always pass `max_turns` — it caps tool-call loops.
- `Runner.run` returns a `RunResult`; the response text is `result.final_output`.
- The MCP fetch tool can only retrieve a URL you give it — it cannot search.
- Agents with `mcp_servers=[...]` must be created **and** run inside the server's `async with` block.
- `@function_tool` replaces the function with a `FunctionTool` object — keep the plain function around if tests need to call it.
- Tests stay hermetic: unit-test the plain tool functions and route registration; running an agent needs `OPENAI_API_KEY`.
