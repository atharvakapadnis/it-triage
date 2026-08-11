import os
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP

# hosting 0.0.0.0 + PORT env for now
mcp = FastMCP(
    "it-triagge-mcp",
    host="0.0.0.0",
    port=int(os.getenv("PORT", 8080)),
)

class PingResult(BaseModel):
    status: str = Field(description="ok if the server is healthy")
    echo: str = Field(description="the message echoed back")

@mcp.tool()
def ping(message: str) -> PingResult:
    """Health check"""
    return PingResult(status="ok", echo=message)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")