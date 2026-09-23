
from src.mcp_server.mcp_server import launch_server
import os

host = os.environ.get("MCP_HOST", "0.0.0.0")
port = int(os.environ.get("MCP_PORT", "8042"))
default_mode = "stdio" if __name__ == "__main__" else "http"
mode = os.environ.get("MCP_MODE", default_mode)

app = launch_server("MBPP", mode, host, port)
