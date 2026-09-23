import os
import sys
import json
from flask import Flask, request, Response

from src.mcp_server.mcp_swebench_core import SWETools
from src.mcp_server.mcp_mbpp_core import MBPPTools
from src.mcp_server.mcp_tools_core import (
    CheckRequestJson,
    CheckRequestParamsList,
    CheckRequestParamsCall,
)


def launch_server(
    type_tools: str, mode: str = "", host: str = "0.0.0.0", port: int = 8042
) -> Flask:

    testbed = os.environ.get("TESTBED_PATH")
    if testbed:
        os.chdir(testbed)

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
        tools = MBPPTools(out_format=out_format, in_format=in_format)
    else:
        raise RuntimeError(
            "Cannot load SWETools or MBPPTools, missing class/module"
        )

    @app.get("/")
    def get_exchange() -> Response:
        return Response(
            "Method Not Allowed",
            status=405,
            mimetype="text/plain",
            headers={"Allow": "POST"},
        )

    @app.post("/")
    def post_exchange() -> Response:

        request_format = """
Use JSON-RPC 2.0 (MCP 2026-07-28) format :
{
    "jsonrpc": "2.0",
    "id": <string|int>,
    "method": <string>,
    "params": { "_meta": {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {}
        }
    }
}

Exemples :

tools/list :
{
    "jsonrpc":"2.0","id":1,"method":"tools/list",
    "params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
    "io.modelcontextprotocol/clientCapabilities":{}}}
}

tools/call :
{
    "jsonrpc":"2.0","id":2,"method":"tools/call",
    "params":{"name":"nom_du_tool","arguments":{"arg1":"valeur"},
    "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
    "io.modelcontextprotocol/clientCapabilities":{}}}
}

server/discover :
{"jsonrpc":"2.0","id":3,"method":"server/discover","params":{}}
"""

        if mode == "stdio":
            input_data = tools.io_input.readline()
            if not input_data:
                sys.exit(0)
        else:
            headers = {
                "MCP-Protocol-Version": request.headers.get(
                    "MCP-Protocol-Version"
                ),
                "Mcp-Method": request.headers.get("Mcp-Method"),
                "Mcp-Name": request.headers.get("Mcp-Name"),
            }
            input_data = request.data
        rid = None

        try:
            data = json.loads(input_data)
            if data.get("id") is not None and isinstance(
                data["id"], (int, str)
            ):
                rid = data["id"]
        except Exception:
            msg = tools.message(
                {
                    "error": {
                        "code": -32700,
                        "message": f"invalid json.{request_format}",
                    }
                }
            )
            return tools.response_error(msg, 400)
        try:
            CheckRequestJson(data=data)
            rid = data["id"]
        except Exception as e:
            if rid:
                msg = tools.message(
                    {
                        "error": {
                            "id": rid,
                            "code": -32600,
                            "message": f"json error {e}.{request_format}",
                        }
                    }
                )
            else:
                msg = tools.message(
                    {
                        "error": {
                            "code": -32600,
                            "message": f"json error {e}.{request_format}",
                        }
                    }
                )
            return tools.response_error(msg, 400)
        if data["method"] not in [
            "tools/list",
            "tools/call",
            "server/discover",
        ]:
            msg = tools.message(
                {
                    "id": rid,
                    "error": {
                        "code": -32601,
                        "message": (
                            f"unknown method {data['method']}; "
                            "possibles: tools/list | tools/call "
                            "| server/discover"
                        )
                    },
                }
            )
            return tools.response_error(msg, 200)

        if data.get("params") is None:
            raise ValueError("key 'params' not defined")

        try:
            match data["method"]:
                case "tools/list":
                    CheckRequestParamsList(data=data["params"])
                case "tools/call":
                    CheckRequestParamsCall(data=data["params"])
                    msg = tools.check_func_args(data["params"])
                    if msg:
                        raise ValueError(msg)
                case "server/discover":
                    CheckRequestParamsList(data=data["params"])
        except Exception as e:
            msg = tools.message(
                {
                    "id": rid,
                    "error": {
                        "code": -32602,
                        "message": f"params error;\n{e}",
                    },
                }
            )
            return tools.response_error(msg, 200)

        if mode != "stdio":
            check_headers = (
                headers["MCP-Protocol-Version"]
                != data["params"]["_meta"][
                    "io.modelcontextprotocol/protocolVersion"
                ]
                or headers["Mcp-Method"] != data["method"]
                or data.get("params")
                and data["params"].get("name") != headers["Mcp-Name"]
            )
            if headers["MCP-Protocol-Version"] != "2026-07-28":
                msg = tools.message(
                    {
                        "id": rid,
                        "error": {
                            "code": -32022,
                            "message": "wrong http-header; unsuported version,"
                            " server use 2026-07-28",
                        },
                    }
                )
                return tools.response_error(msg, 400)

            if check_headers:
                msg = tools.message(
                    {
                        "id": rid,
                        "error": {
                            "code": -32020,
                            "message": "http header(s) missing "
                            f"or not match the body: {headers}",
                        },
                    }
                )
                return tools.response_error(msg, 400)

        match data["method"]:
            case "tools/list":
                send_data = tools.model
                send_data["id"] = rid
                msg = tools.message(send_data)
                return tools.response(msg)
            case "tools/call":
                return tools.response(
                    tools.tools_call(data["params"], data),
                    content="text/event-stream",
                )
            case "server/discover":
                minimal_discover = {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "resultType": "complete",
                        "supportedVersions": ["2026-07-28"],
                        "capabilities": {"tools": {}},
                        "ttlMs": 86400000,
                        "cacheScope": "private",
                    },
                }
                msg = tools.message(minimal_discover)
                return tools.response(msg)

        msg = tools.message(
            {
                "id": rid,
                "error": {
                    "code": -32603,
                    "message": "impossible error encounter",
                },
            }
        )
        return tools.response_error(msg, 200)

    if mode == "stdio":

        def main() -> None:
            try:
                while 1:
                    post_exchange()
            except Exception as e:
                print(f"server crashed with error : {e}", file=sys.stderr)

        main()
    return app
