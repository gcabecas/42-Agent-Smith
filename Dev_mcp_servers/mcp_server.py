
import sys
import json
from typing import Any, Literal, Optional, Callable, Generator
from flask import Flask, request, Response

from mcp_swebench_core import SWETools
from mcp_tools_core import CheckRequestKeys, CheckRequestParams

def launch_server(type_tools: str, mode: str = "", port: int = 8042, host: str = "0.0.0.0") -> None:

    if mode == "stdio":
        out_format = "stdio"
        in_format = "stdio"
    else:
        out_format = "http"
        in_format = "http"
    app = Flask(__name__)
    if type_tools == "SWE":
        tools = SWETools(out_format=out_format, in_format=in_format)
    elif type_tools == "MBPP":
        #tools = MBPPTools(out_format="http", in_format="http")
        pass
    else:
        raise RuntimeError("Cannot load SWETools or MBPPTools, missing class/module")


    @app.get("/")
    def get_exchange() -> Response:
        return Response(
                        "Method Not Allowed", status=405,
                        mimetype="text/plain", headers={"Allow": "POST"}
                        )


    @app.post("/")
    def post_exchange() -> Response:

        request_format = """
    Format JSON-RPC 2.0 (MCP 2026-07-28) :

    {
      "jsonrpc": "2.0",
      "id": <string|int>,
      "method": <string>,
      "params": { "_meta": {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}
      }, ... }
    }

    Exemples :

    tools/list :
    {"jsonrpc":"2.0","id":1,"method":"tools/list",
     "params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
     "io.modelcontextprotocol/clientCapabilities":{}}}}

    tools/call :
    {"jsonrpc":"2.0","id":2,"method":"tools/call",
     "params":{"name":"nom_du_tool","arguments":{"arg1":"valeur"},
     "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
     "io.modelcontextprotocol/clientCapabilities":{}}}}

    server/discover :
    {"jsonrpc":"2.0","id":3,"method":"server/discover","params":{}}"""

        if mode == "stdio":
            input_data = input(tools.io_input)
        else:
            input_data = request.data

        try:
            data = json.loads(request.data)
        except Exception as e:
            msg = tools.message({"error": {"code": -32700, "message": "invalid json"}})
            return tools.response_error(msg)
        try:
            valid1 = CheckRequestKeys(data=data)
        except Exception as e:
            msg = tools.message({"error": {"code": -32600, "message": f"json keys error;{request_format}"}})
            return tools.response_error(msg)
        if data["method"] not in ["tools/list", "tools/call", "server/discover"]:
            msg = tools.message({"error": {"code": -32601, "message": "unknow method; possibles: tools/list | tools/call | server/discover   "}})
            return tools.response_error(msg)
        try:
            valid2 = CheckRequestParams(data=data)
        except Exception as e:
            print(e)
            msg = tools.message({"error": {"code": -32602, "message": f"json arguments error;{request_format}"}})
            return tools.response_error(msg)

        match data["method"]:
            case "tools/list":
                pass
            case "tools/call":
                return Response(tools.tools_call(data["params"]))
            case "server/discover":
                pass

        return Response("")


    def main() -> None:
        try:
            if mode == "stdio":
                while 1:
                    post_exchange()
            else:
                app.run(host=host, port=port)
        except Exception as e:
            print(f"server crashed with error : {e}", file=sys.stderr)

    main()


minimal_discover = {
  "jsonrpc": "2.0",
  "id": "discover-1",
  "result": {
    "resultType": "complete",
    "supportedVersions": ["2026-07-28"],
    "capabilities": { "tools": {} },
    "ttlMs": 3600000,
    "cacheScope": "public"
  }
}

