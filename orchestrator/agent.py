import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8080/mcp")

def _mcp_auth_headers(url: str) -> dict:
    """Mint a Google ID token for the MCP server when it's a real Cloud Run URL.
    Local (localhost) needs no auth, so we skip it there."""
    if "run.app" not in url:
        return {}
    import google.auth.transport.requests
    import google.oauth2.id_token
    # audience = the MCP service's base URL (scheme+host), NOT the /mcp path
    audience = url.split("/mcp")[0]
    req = google.auth.transport.requests.Request()
    token = google.oauth2.id_token.fetch_id_token(req, audience)
    return {"Authorization": f"Bearer {token}"}


async def _call_mcp(tool_name: str, args: dict) -> dict:
    """Open a short-lived MCP session, call one tool, return its structured result."""
    headers = _mcp_auth_headers(MCP_SERVER_URL)
    async with streamablehttp_client(MCP_SERVER_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            return result.structuredContent

# LOCAL_MCP_URL = "http://127.0.0.1:8080/mcp"

# async def _call_mcp(tool_name: str, args: dict) -> dict:
#     """Open a short-lived MCP session, call one tool, return its structured result."""
#     async with streamablehttp_client(LOCAL_MCP_URL) as (read, write, _):
#         async with ClientSession(read, write) as session:
#             await session.initialize()
#             result = await session.call_tool(tool_name, args)
#             return result.structuredContent

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

# --- Hardware domain tools -------------------------------------------------

async def get_asset_status(asset_id: str) -> dict:
    """Diagnose a hardware asset by its id. Returns status 'not_found' if it isn't in inventory."""
    return await _call_mcp("get_asset_status", {"asset_id": asset_id})

async def open_hardware_ticket(asset_id: str, issue_summary: str, user_id: str) -> dict:
    """Open a hardware support ticket. Use as a fallback when an asset can't be diagnosed or is failed."""
    return await _call_mcp(
        "open_hardware_ticket",
        {"asset_id": asset_id, "issue_summary": issue_summary, "user_id": user_id},
    )

hardware_agent = LlmAgent(
    name="hardware_agent",
    model="gemini-2.5-flash",
    description="Handles device and hardware issues (laptops, monitors, peripherals).",
    instruction=(
        "You are an IT hardware specialist. Diagnose the device problem, then act.\n"
        "1. Use get_asset_status to look up the asset by its id.\n"
        "2. If the asset is NOT found, or its condition is 'failed', open a hardware "
        "ticket with open_hardware_ticket so a technician follows up — do not dead-end.\n"
        "3. Report clearly what you found and what you did (include any ticket id).\n"
        "Assume the user's id is u_1001 unless told otherwise."
    ),
    tools=[get_asset_status, open_hardware_ticket],
)

# --- Licensing domain tools ------------------------------------------------

async def check_license_inventory(software: str) -> dict:
    """Diagnose license seat availability for a piece of software."""
    return await _call_mcp("check_license_inventory", {"software": software})

async def request_license_approval(software: str, user_id: str, justification: str) -> dict:
    """Request approval for a software license. May be denied by policy."""
    return await _call_mcp(
        "request_license_approval",
        {"software": software, "user_id": user_id, "justification": justification},
    )

licensing_agent = LlmAgent(
    name="licensing_agent",
    model="gemini-2.5-flash",
    description="Handles software license requests, including the approval step.",
    instruction=(
        "You are an IT licensing specialist. Handle the license request end to end.\n"
        "1. Use check_license_inventory to see whether seats are available.\n"
        "2. Use request_license_approval to submit the request.\n"
        "3. If approval is DENIED, explain the denial reason clearly and do not "
        "pretend it succeeded. If approved, report the request id.\n"
        "Assume the user's id is u_1001 unless told otherwise."
    ),
    tools=[check_license_inventory, request_license_approval],
)

# --- Root orchestrator (agents-as-tools) -----------------------------------

root_agent = LlmAgent(
    name="root_orchestrator",
    model="gemini-2.5-flash",
    description="Classifies IT requests, routes to specialists, and synthesizes one reply.",
    instruction=(
        "You are the root IT support orchestrator. You do NOT solve problems "
        "yourself — you route to specialists and merge their results.\n"
        "Available specialists (call them as tools):\n"
        "- access_agent: account, VPN, and drive access issues.\n"
        "- hardware_agent: device/hardware issues (laptops, monitors, peripherals).\n"
        "- licensing_agent: software license requests and approvals.\n\n"
        "Steps:\n"
        "1. Read the request and decide which specialist(s) it needs. A request "
        "may span MORE THAN ONE domain — if so, call each relevant specialist.\n"
        "2. Pass each specialist the part of the request relevant to it.\n"
        "3. Synthesize ONE coherent reply that combines what every specialist did. "
        "Do not just concatenate — write a single clear response to the user."
    ),
    tools=[
        AgentTool(agent=access_agent),
        AgentTool(agent=hardware_agent),
        AgentTool(agent=licensing_agent),
    ],
)