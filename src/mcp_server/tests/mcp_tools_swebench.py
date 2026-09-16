
from src.mcp_server.mcp_server import launch_server
import sys
import os

host = os.environ.get("MCP_HOST", "0.0.0.0")
port = int(os.environ.get("MCP_PORT", "8042"))
mode = os.environ.get("MCP_MODE", "http")

app = launch_server("SWE", mode, host, port)
