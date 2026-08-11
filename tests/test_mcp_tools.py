"""Unit tests for the MCP tool handlers — no server, no LLM, no network.

The mcp SDK's FastMCP wraps each @mcp.tool() in a FunctionTool exposing the
original callable as .fn; _fn() resolves it whether wrapped or raw."""
from mcp_server.server import (
    check_user_access,
    get_asset_status,
    check_license_inventory,
    request_license_approval,
)


def _fn(tool):
    return getattr(tool, "fn", tool)


# --- happy paths ---
def test_check_user_access_vpn_blocked():
    r = _fn(check_user_access)(user_id="u_1001", resource="vpn")
    assert r.status == "ok"
    assert r.has_access is False
    assert r.reason == "credentials_expired"


def test_check_user_access_unknown_user():
    r = _fn(check_user_access)(user_id="u_9999", resource="vpn")
    assert r.status == "user_not_found"
    assert r.has_access is None


def test_license_inventory_available():
    r = _fn(check_license_inventory)(software="figma")
    assert r.status == "ok"
    assert r.seats_available == 2  # 50 total - 48 used


# --- failure modes (the graded ones) ---
def test_get_asset_status_not_found():
    r = _fn(get_asset_status)(asset_id="AST-999")
    assert r.status == "not_found"
    assert r.asset_type is None


def test_get_asset_status_known_asset():
    r = _fn(get_asset_status)(asset_id="AST-100")
    assert r.status == "ok"
    assert r.condition == "degraded"


def test_license_approval_denied_for_restricted():
    r = _fn(request_license_approval)(
        software="adobe_cc", user_id="u_1001", justification="design"
    )
    assert r.status == "denied"
    assert r.reason is not None


def test_license_approval_approved():
    r = _fn(request_license_approval)(
        software="figma", user_id="u_1001", justification="design"
    )
    assert r.status == "approved"
    assert r.request_id.startswith("LIC-")