import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import datetime
from agents import Agent, Runner, function_tool
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

from api.helpers.bigquery_helper import bq_helper
from api.helpers.gcs_helper import gcs_helper

hello = APIRouter()

load_dotenv()

@hello.get("/hello_world")
def hello_world():
    return {"message": f"Hello, World! - {datetime.now().isoformat()}"}


@hello.get("/gcp_check")
def gcp_check():
    # Proves the deployed service can reach BigQuery and GCS. Each half reports
    # independently — always 200, so a failure shows which side broke and why
    # instead of a bare 500.
    bq_ok, _, bq_err = bq_helper.run_select("SELECT 1 AS ping")
    gcs_ok, _, gcs_err = gcs_helper.list_files()
    return {
        "bigquery": {
            "status": "ok" if bq_ok else "error",
            "detail": bq_err or f"queried {bq_helper.project_id}.{bq_helper.dataset_id}",
        },
        "gcs": {
            "status": "ok" if gcs_ok else "error",
            "detail": gcs_err or f"listed gs://{gcs_helper.bucket_name}",
        },
    }

@hello.get("/", response_class=HTMLResponse)
def landing_page():
    return """<html>
  <head><title>Vocal Bridge Training API</title></head>
  <body>
    <h1>Vocal Bridge Training API</h1>
    <p>Voice-agent backend for "The Complete Trip" hackathon (Sabre + Vocal Bridge).</p>
    <ul>
      <li><a href="/docs">Interactive API docs</a></li>
      <li><a href="/v1/hello/hello_world">Health: hello_world</a></li>
      <li><a href="/v1/hello/gcp_check">Health: gcp_check (BigQuery + GCS)</a></li>
      <li><a href="/v1/vb_test/">Testing Vocal Bridge (live-call smoke test)</a></li>
      <li>Concurrency spike (Phase 5): POST /v1/concurrency_spike/talk_while_tool_runs and POST /v1/concurrency_spike/cascade (see /docs)</li>
      <li>Sabre tools (Phase 6): POST /v1/sabre_tools/seed_trip, POST /v1/disruption/break_flight, POST /v1/sabre_tools/repair_trip (see /docs)</li>
    </ul>
    <h2>Course lesson demos (Phase 7)</h2>
    <ul>
      <li>L2 — Voice in your App: <a href="/v1/vb_test/">live web-client call</a> (token mint + managed widget)</li>
      <li>L2/L3 — Cascaded architecture: <a href="/docs#/cascade_demo">/v1/cascade_demo</a> (STT, LLM, TTS stages + full /converse; /llm is the L3 query-server pattern)</li>
      <li>L4 — Voice as a Tool: <a href="/docs#/outbound_call">/v1/outbound_call</a> (place a real outbound call, inspect status, archive the recording)</li>
    </ul>
  </body>
</html>"""


# The fetch server is a Python package (mcp-server-fetch), so run it in-process
# with the container's own interpreter — no `uvx`/`uv` needed.
fetch_server_params = {
        "command": "python",
        "args": ["-m", "mcp_server_fetch"],
    }


@hello.get("/agents")
async def run_agents():
    # The agent must be created and run *inside* the `async with`, while the
    # MCP server subprocess is connected.
    async with MCPServerStdio(name="Fetch Server", params=fetch_server_params,
                              client_session_timeout_seconds=60) as server:
        tools = await server.list_tools()
        print(tools)

        PROMPT = """You are a helpful assistant.
        When the users asks about a web page, if you can accerss the internet,
        then read it first, then answer based on what you actually read.
        Always cite the URL
        If you cannot access the internet, say so."""

        agent = Agent(
            name="MyAgent",
            model="gpt-5.4-mini",
            instructions=PROMPT,
            mcp_servers=[server],
        )

        # Runner.run is a classmethod — you don't instantiate Runner.
        # The fetch tool can only retrieve a URL you give it — it can't search.
        # So point it at the episode page directly, like the course did.
        result = await Runner.run(
            agent,
            "What is the episode at https://www.superdatascience.com/1000 about?",
            max_turns=10,
        )

    # result is a RunResult; return the serializable text.
    return {"result": result.final_output}


SANDBOX_DIR = os.path.abspath("temp_file_storage")

#os.makedirs(SANDBOX_DIR, exist_ok=True)
## try except if exists
try:
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    print(f"Sandbox directory {SANDBOX_DIR} created or already exists.")
except Exception as e:
    print(f"Error creating sandbox directory {SANDBOX_DIR}: {e}")
    raise
# Our own Python filesystem MCP server (no Node/npx needed). Absolute path so it
# resolves regardless of the subprocess cwd.
_FS_SERVER = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "mcp_servers", "filesystem_server.py")

filesystem_server_params = {
    "command": "python",
    "args": [_FS_SERVER, SANDBOX_DIR],
}

@hello.get("/agents_with_mcp_filesystem")
async def run_agents_with_mcp_filesystem():
    # The agent must be created and run *inside* the `async with`, while the
    # MCP server subprocess is connected.
    async with MCPServerStdio(name="Filesystem Server", params=filesystem_server_params,
                              client_session_timeout_seconds=60) as server:
        fs_tools = await server.list_tools()
        for tool in fs_tools:
            print(tool)

        FILES_AGENT_PROMPT = f"""You are a file assistant. You work inside the directory {SANDBOX_DIR}.
        Always use FULL paths under {SANDBOX_DIR} (e.g. {SANDBOX_DIR}/notes.txt).
        You have filesystem tools (via an MCP server) to list, read, search, write, and edit files.
        When asked about files, first list or read what's there, then act based on what you actually
        find. Be concise, and tell the user exactly which files you read or changed."""

        agent = Agent(
            name="Files Agent",
            model="gpt-5.4-mini",
            instructions=FILES_AGENT_PROMPT,
            mcp_servers=[server],
        )

        result = await Runner.run(
            agent,
            input="What files are in my folder, and what is each one about? Give me a concise summary.",
            max_turns=10,
        )

    # result is a RunResult; return the serializable text.
    return {"result": result.final_output}

# Fictitious weather data — no real API behind it. Kept as a plain function so
# tests can call it directly; @function_tool would replace it with a FunctionTool
# object that is no longer callable as Python.
def _get_weather(city: str) -> str:
    """Get the current weather for a city."""
    if "delano" in city.lower():
        return "The weather in Delano, MN is sunny and 60°F."
    return f"Sorry, I only have weather data for Delano, MN — not {city}."


get_weather = function_tool(_get_weather)


@hello.get("/agents_with_function_tool")
async def run_agents_with_function_tool():
    # Function tools need no MCP server subprocess — pass them straight to the
    # Agent via tools=[...]. The SDK builds the JSON schema from the signature
    # and docstring.
    agent = Agent(
        name="Weather Agent",
        model="gpt-5.4-mini",
        instructions="You are a helpful assistant. Use the get_weather tool "
                     "to answer weather questions.",
        tools=[get_weather],
    )

    # Runner.run is a classmethod — you don't instantiate Runner.
    result = await Runner.run(
        agent,
        "What is the weather in Delano, MN?",
        max_turns=10,
    )

    # result is a RunResult; return the serializable text.
    return {"result": result.final_output}


@hello.get("/agents_no_mcp")
async def run_agents_no_mcp():
    # This is a simplified version of the agent run without MCP server
    PROMPT = """You are a helpful assistant.
    When the users asks about a web page, if you can accerss the internet,
    then read it first, then answer based on what you actually read.
    Always cite the URL
    If you cannot access the internet, say so."""

    agent = Agent(
        name="MyAgent",
        model="gpt-5.4-mini",
        instructions=PROMPT,
    )

    # Runner.run is a classmethod — you don't instantiate Runner.
    result = await Runner.run(agent, "Hello, Where did the Minnesota Vikings play?", max_turns=10)

    # result is a RunResult; return the serializable text.
    return {"result": result.final_output}