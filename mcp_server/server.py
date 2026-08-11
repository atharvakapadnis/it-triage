"""
IT Support Triage MCP Server
Exposes the tools the three agents will call. Mocked with in memory dicts AMOG US, shaped like IT systems.
Each tool has typed inputs, returns typed Pydantic model (MCP emits structured content) and reports outcome via status field the agent branches on.
Two tools carrying failure mode - deliberate
get_asset_status -> not found
request_license_approval -> denied
Returned as data not exceptions, to fail gracefully and allow agent to reason over the failure and take fallback actions.
"""

import os
import random
import string
from typing import Literal, Optional

from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "it-triage-mcp",
    host="0.0.0.0",
    port=int(os.getenv("PORT", 8080)),
)

# --------------
# Mock Backends
# --------------

_USER_ACCESS = {
    "u_1001": {"vpn": False, "shared_drive": True, "email": True},
    "u_1002": {"vpn": True, "shared_drive": False, "email": True},
}

_ASSETS = {
    "AST-100": {"asset_type": "laptop", "assigned_to": "u_1001",
                "condition": "degraded", "warranty_active": True},
    "AST-200": {"asset_type": "monitor", "assigned_to": "u_1002",
                "condition": "healthy", "warranty_active": False},
    # asset_id not listed above = status = "not_found" for failure mode
}

_LICENSES = {
    "figma": {"seats_total": 50, "seats_used": 48},
    "slack": {"seats_total": 200, "seats_used": 120},
    "adobe_cc": {"seats_total": 10, "seats_used": 10},
}

# mock policy auto denies (to simulate approval denied)
_RESTRICTED_SOFTWARE = {"adobe_cc"}

def _rand(prefix: str, n: int, digits_only: bool = False) -> str:
    pool = string.digits if digits_only else string.ascii_lowercase + string.digits
    return prefix + "".join(random.choices(pool, k=n))

# --------------
# Health check
# --------------

class PingResult(BaseModel):
    status: str = Field(description="ok if server healthy")
    echo: str = Field(description="the message echoed back")

@mcp.tool()
def ping(message: str) -> PingResult:
    """Health check, for deployment smoke tests"""
    return PingResult(status="ok", echo=message)

# --------------
# Access domain
# --------------

class AccessCheck(BaseModel):
    status: Literal["ok", "user_not_found"] = Field(
        description="ok, or user_not_found if user id is unknown"
    )
    user_id: str
    resource: str = Field(description="the resource that was checked")
    has_access: Optional[bool] = Field(
        default=None, description="whether the user has access, null if user not found"
    )
    reason: Optional[str] = Field(
        default=None, description="why access is blocked, when has_access is false"
    )

@mcp.tool()
def check_user_access(
    user_id: str,
    resource: Literal["vpn", "shared_drive", "email"],
) -> AccessCheck:
    """Check if user currently has access to a resource"""
    user = _USER_ACCESS.get(user_id)
    if user is None:
        return AccessCheck(status="user_not_found", user_id=user_id, resource=resource)
    has = user.get(resource, False)
    return AccessCheck(
        status="ok", user_id=user_id, resource=resource,
        has_access=has, reason=None if has else "credentials_expired",
    )

class VpnReset(BaseModel):
    status: Literal["reset"] = Field(description="reset when new credentials were issued")
    user_id: str
    temporary_password: str = Field(description="one-time temporary VPN password")
    expires_in_hours: int = Field(description="how long the temporary password is valid")

@mcp.tool()
def reset_vpn_credentials(user_id: str) -> VpnReset:
    """Issues new temp VPN password. User after diagnosis shows VPN access is blocked."""
    return VpnReset(
        status="reset", user_id=user_id,
        temporary_password=_rand("vpn-",8), expires_in_hours=24,
    )

# --------------
# Hardware domain
# --------------

class AssetStatus(BaseModel):
    status: Literal["ok", "not_found"] = Field (
        description="ok, or not_found if asset id not in inventory"
    )
    asset_id: str
    asset_type: Optional[str] = Field(default=None)
    assigned_to: Optional[str] = Field(default=None)
    condition: Optional[Literal["healthy", "degraded", "failed"]] = Field(default=None)
    warranty_active: Optional[bool] = Field(default=None)

@mcp.tool()
def get_asset_status(asset_id: str) -> AssetStatus:
    """Diagnose a hardware asset by id. Returns status='not_found' if it isn't in inventory."""
    rec = _ASSETS.get(asset_id)
    if rec is None:
        return AssetStatus(status="not_found", asset_id=asset_id)
    return AssetStatus(status="ok", asset_id=asset_id, **rec)

class HardwareTicket(BaseModel):
    status: Literal["created"] = Field(description="created when a ticket is opened")
    ticket_id: str
    priority: Literal["low", "normal", "high"]
    eta_business_days: int

@mcp.tool()
def open_hardware_ticket(asset_id: str, issue_summary: str, user_id: str) -> HardwareTicket:
    """Open a hardware ticket, fallback when an asset cannot be diagnosed"""
    return HardwareTicket(
        status="created", ticket_id=_rand("HW-", 4, digits_only=True),
        priority="normal", eta_business_days=2,
    )

# --------------
# Licensing domain
# --------------

class LicenseInventory(BaseModel):
    status: Literal["ok", "unknown_software"] = Field(
        description="ok, or unknown_software if not tracked"
    )
    software: str
    seats_total: Optional[int] = Field(default=None)
    seats_used: Optional[int] = Field(default=None)
    seats_available: Optional[int] = Field(default=None)

@mcp.tool()
def check_license_inventory(software: str) -> LicenseInventory:
    """Diagnose license seat availability."""
    inv = _LICENSES.get(software.lower())
    if inv is None:
        return LicenseInventory(status="unknown_software", software=software)
    return LicenseInventory(
        status="ok", software=software,
        seats_total=inv["seats_total"], seats_used=inv["seats_used"],
        seats_available=inv["seats_total"] - inv["seats_used"],
    )

class LicenseApproval(BaseModel):
    status: Literal["approved", "denied"] = Field(
        description="approved or denied by the approval policy"
    )
    request_id: str
    software: str
    user_id: str
    approver: str = Field(description="who or what policy made the decision")
    reason: Optional[str] = Field(default=None, description="why the request was denied")

@mcp.tool()
def request_license_approval(software: str, user_id: str, justification: str) -> LicenseApproval:
    """Request approval for a software license. Restricted software is denied by policy (agent must handle)"""
    req = _rand("LIC-", 4, digits_only=True)
    if software.lower() in _RESTRICTED_SOFTWARE:
        return LicenseApproval(
            status="denied", request_id=req, software=software, user_id=user_id,
            approver="policy_engine", reason="exceed_per_seat_budget_requires_director_signoff",
        )
    return LicenseApproval(
        status="approved", request_id=req, software=software, user_id=user_id,
        approver="auto_approver"
    )

if __name__ == "__main__":
    mcp.run(transport="streamable-http")