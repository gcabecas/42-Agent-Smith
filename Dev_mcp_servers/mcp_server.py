
import sys
import json
from typing import Any, Literal, Optional, Callable, Generator
from flask import Flask, request, Response
from pydantic import ValidationError

from mcp_swebench_core import SWETools
from mcp_tools_core import CheckRequestJson, CheckRequestParamsList, CheckRequestParamsCall

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
            return tools.response_error(msg, 400)
        try:
            valid1 = CheckRequestJson(data=data)
        except Exception as e:
            msg = tools.message({"error": {"code": -32600, "message": f"json error;{request_format}"}})
            return tools.response_error(msg, 400)
        if data["method"] not in ["tools/list", "tools/call", "server/discover"]:
            msg = tools.message({"error": {"code": -32601, "message": "unknow method; possibles: tools/list | tools/call | server/discover   "}})
            return tools.response_error(msg, 200)

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
                    if "params" in data.keys():
                        raise ValueError("<params> key is useless and forbiden in server/discoover method")
        except ValidationError as exc:
            first = exc.errors()[0]
            
            if first["type"] == "value_error":
                msg = first["msg"].split("Value error,")[-1].split("[type=")[0].strip(" ('\"")
            else:
                msg = str(exc)
            if "For further information" in msg.splitlines()[-1]:
                msg = "\n".join(msg.splitlines()[:-1])
            msg_data = tools.message({"error": {"code": -32602, "message": msg}})
            return tools.response_error(msg_data, 200)
        except Exception as e:
            msg = tools.message({"error": {"code": -32602, "message": f"params error;\n{e}"}})
            return tools.response_error(msg, 200)

        match data["method"]:
            case "tools/list":
                return Response(tools.model)
            case "tools/call":
                return Response(tools.tools_call(data["params"], data))
            case "server/discover":
                minimal_discover = {
                  "jsonrpc": "2.0",
                  "id": "discover-1",
                  "result": {
                    "resultType": "complete",
                    "supportedVersions": ["2026-07-28"],
                    "capabilities": { "tools": {} },
                  }
                }
                msg = tools.message(minimal_discover)
                return Response(msg)

        msg = tools.message({"error": {"code": -32603, "message": f"impossible error encounter"}})
        return tools.response_error(msg, 200)


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



