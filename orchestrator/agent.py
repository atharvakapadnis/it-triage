import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from google.adk.agents import LlmAgent

LOCAL_MCP_URL = "http://127.0.0.1:8080/mcp"

async def _call_mcp(tool_name: str, args: dict) -> dict:
    """Open a short-lived MCP session, call one tool, return its structured result."""
    async with streamablehttp_client(LOCAL_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            return result.structuredContent

# --- Access domain tools, as plain ADK functions -------------------------
# Clean signatures + docstrings -> ADK builds simple declarations Gemini won't
# code-mode on. Each just proxies to the real MCP server.

async def check_user_access(user_id: str, resource: str) -> dict:
    """Check whether a user has access to a resource (vpn, shared_drive, or email)."""
    return await _call_mcp("check_user_access", {"user_id": user_id, "resource": resource})

async def reset_vpn_credentials(user_id: str) -> dict:
    """Issue a new temporary VPN password for a user whose VPN access is blocked."""
    return await _call_mcp("reset_vpn_credentials", {"user_id": user_id})

access_agent = LlmAgent(
    name="access_agent",
    model="gemini-2.5-flash",
    description="Handles account, VPN, and drive access issues.",
    instruction=(
        "You are an IT access specialist. Diagnose the user's access problem, then act.\n"
        "- Check whether the user has access to the relevant resource "
        "(vpn, shared_drive, or email).\n"
        "- If VPN access is blocked, reset their VPN credentials to issue a temporary password.\n"
        "- Then reply in plain language: what you found, what you did, and any temporary "
        "password and its expiry.\n"
        "The user's id is u_1001 unless they say otherwise."
    ),
    tools=[check_user_access, reset_vpn_credentials],
)