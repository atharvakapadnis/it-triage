import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def call(session, name, args):
    r = await session.call_tool(name, args)
    print(f"\n{name}({args})")
    print("  isError:", r.isError)
    print("  structured:", r.structuredContent)

async def main():
    async with streamablehttp_client("http://127.0.0.1:8080/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            await call(session, "check_user_access", {"user_id": "u_1001", "resource": "vpn"})
            await call(session, "reset_vpn_credentials", {"user_id": "u_1001"})
            await call(session, "get_asset_status", {"asset_id": "AST-999"})   # not_found
            await call(session, "request_license_approval",
                       {"software": "adobe_cc", "user_id": "u_1001", "justification": "design work"})  # denied

asyncio.run(main())