
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)

mcp = FastMCP("FRIDAY")

@mcp.tool()
def get_current_time() -> dict:
    """Get the current date and time in India."""
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return {
        "timezone": "Asia/Kolkata",
        "date": now.strftime("%d-%m-%Y"),
        "time": now.strftime("%I:%M:%S %p")
    }

@mcp.tool()
def friday_status() -> dict:
    """Check whether the FRIDAY MCP service is running."""
    return {
        "assistant": "FRIDAY",
        "status": "online"
    }

if __name__ == "__main__":
    mcp.run(transport="stdio")
