"""Phase 2 tests for the get_weather function-tool example.

Hermetic like the rest of the suite: the underlying weather function is plain
Python (no OpenAI call), and the endpoint itself is only checked for route
registration — running the agent would need OPENAI_API_KEY.
"""
from agents import FunctionTool

import main
from api.hello import _get_weather, get_weather


def test_weather_for_delano_is_60f():
    answer = _get_weather("Delano, MN")
    assert "Delano, MN" in answer
    assert "60°F" in answer


def test_weather_delano_case_insensitive():
    assert "60°F" in _get_weather("delano")


def test_weather_unknown_city_declines():
    answer = _get_weather("Tokyo")
    assert "60°F" not in answer
    assert "Tokyo" in answer


def test_get_weather_is_a_function_tool():
    # The wrapped object is what gets passed to Agent(tools=[...]).
    assert isinstance(get_weather, FunctionTool)


def test_function_tool_route_registered():
    paths = main.app.openapi()["paths"]
    assert "/v1/hello/agents_with_function_tool" in paths
