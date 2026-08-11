"""Integration test: real routing through the root orchestrator.

Requires a local MCP server on :8080 and Vertex ADC. Excluded from CI via the
'integration' marker; run locally with:  pytest -m integration
"""
import os
import sys
import pytest

pytest.importorskip("google.adk")  # keeps CI collection clean when ADK isn't installed
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orchestrator"))

pytestmark = pytest.mark.integration

from agent import root_agent  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402


async def _routed_agents(message: str) -> list[str]:
    sessions = InMemorySessionService()
    await sessions.create_session(app_name="t", user_id="u_1001", session_id="s")
    runner = Runner(agent=root_agent, app_name="t", session_service=sessions)
    msg = types.Content(role="user", parts=[types.Part(text=message)])
    called = []
    async for event in runner.run_async(user_id="u_1001", session_id="s", new_message=msg):
        if event.author == root_agent.name:
            for call in (event.get_function_calls() or []):
                called.append(call.name)
    return called


async def test_single_domain_routes_to_hardware():
    agents = await _routed_agents("My laptop, asset AST-100, keeps freezing.")
    assert "hardware_agent" in agents
    assert "access_agent" not in agents


async def test_fanout_routes_to_two_specialists():
    agents = await _routed_agents(
        "I can't connect to the VPN, and I also need a Figma license approved."
    )
    assert "access_agent" in agents
    assert "licensing_agent" in agents