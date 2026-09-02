
# USING MCP VERSION 2026-07-28

from typing import Any, Literal, Optional, Callable
import sys
import os
from io import TextIOWrapper
import json
from pydantic import BaseModel, model_validator
from flask import Flask, request, Response
#from flask_sock import Sock

PORT = 8042
HOST = "0.0.0.0"

SDTIO_MOD = False

def placeholder(*args, **kwargs) -> None:
    pass

class McpCore(BaseModel):

    out_format: str
    in_format: str
    io_output: Any = sys.stdout
    io_error: Any = sys.stderr
    io_input: Any = sys.stdin

    methods: dict[str: Any] = {"init": 0}
    response: Callable[..., None] = placeholder
    response_error: Callable[..., None] = placeholder

    @model_validator(mode="after")
    def checks_after(self) -> "McpCore":
        if not isinstance(self.io_output, TextIOWrapper):
            raise ValueError(f"{self.io_output} not valid TextIOWrapper")
        if not isinstance(self.io_error, TextIOWrapper):
            raise ValueError(f"{self.io_error} not valid TextIOWrapper")

        if self.out_format not in ["http", "stdio"]:
            raise ValueError("out_format invalid, possible : http | stdio")
        if self.in_format not in ["http", "stdio"]:
            raise ValueError("in_format invalid, possible : http | stdio")

        if self.out_format == "http":
            def response(msg: str) -> Response:
                return Response(msg)
            def response_error(msg: str) -> Response:
                return Response(msg)
        else:
            def response(msg: str) -> None:
                print(msg, file=self.io_output)
            def response_error(msg: str) -> None:
                print(f"error occured:", msg, file=self.io_error)
        self.response = response
        self.response_error = response_error

        return self
    
    def message(self, infos: set[dict[str: Any]]) -> str:
        base = {"jsonrpc": "2.0"}
        base.update(infos)
        return json.dumps(base)

    def check_args(self, func: dict[str, Any]) -> dict[str, Any]:
        log = ""
        return {"test": 0}
#        if func["name"] not in self.methods.keys()
#            tool.response_error("unknow function used", XXX)
        #for name, args in self.methods[func["name"]].items():

        return # x

class RequestKeys(BaseModel):
    jsonrpc: Literal["2.0"]
    id: Any
    method: Any
    params: Optional[Any] | None = None

class CheckRequestKeys(BaseModel):
    data: RequestKeys

class RequestParams(BaseModel):
    jsonrpc: Literal["2.0"]
    id: str | int
    method: str
    params: Optional[dict[str, Any]] | None = None

class CheckRequestParams(BaseModel):
    data: RequestParams






# TOOLS ---------------------------------------//

from threading import Thread
import time

RESPONSE_MUTEX = threading.Lock()

class SWETools(McpCore):

    def __init__(self, *args, **kwargs) -> None:
        methods = {
                "read_file" : {"filepath": {"str"}, "start_line": {"str", "int"}, "end_line": {"str", "int"}},
                "edit_file" : {"filepath": {"str"}, "old_str": {"str"}, "new_str": {"str"}},
                "list_files" : {"directory": {"str"}, "pattern": {"str"}},
                "search_code" : {"pattern": {"str"}, "file_pattern": {"str"}},
                "search_function_or_class_definition_in_code" : {"name": {"str"}},
                "find_references" : {"name": {"str"}, "filepath": {"str"}, "line": {"str", "int"}},
                "run_tests" : {},
                "get_patch" : {},
                "run_command" : {"command": {"str"}, "workdir": {"str"}}
        }
        super().__init__(*args, methods=methods, **kwargs)

    def read_file(self, filepath, start_line, end_line):
        pass

    def edit_file(self, filepath, old_str, new_str):
        pass

    def list_files(self, directory, pattern):
        pass



    def search_code(self, pattern, file_pattern):
        pass

    def search_function_or_class_definition_in_code(self, name):
        pass

    def find_references(self, name, filepath, line):
        pass



    def run_tests(self):

        Response()

    def get_patch(self):
        pass

    def run_command(self, command, workdir):
        pass


    def gen_response(self, func: dict[str, Any]) -> Generator[str, None, str]:
        if func.get("arguments") and func["arguments"]:
            thread = Thread(target=getattr(self, func["name"]), kwargs=func[arguments])
        else:
            thread = Thread(target=getattr(self, func["name"]))
        
        thread.start()
        while 1:
            time.sleep(0.01)
            RESPONSE_MUTEX.acquire()
            if not thread.is_alive():
                break
            yield Response() # TODO CREATE RESPONSE FUNC
            RESPONSE_MUTEX.release()


app = Flask(__name__)
tools = SWETools(out_format="http", in_format="http")


@app.get("/")
def get_exchange() -> Response:
    return Response(
                    "Method Not Allowed", status=405,
                    mimetype="text/plain", headers={"Allow": "POST"}
                    )


@app.post("/")
def post_exchange() -> Response:
    global STDIO_MODE

    request_format = """
Post format:
{
  jsonrpc: "2.0";
  id: string | number;
  method: string;
  params?: {
    [key: string]: unknown;
  };
}
"""
    if STDIO_MODE:
        input_data = input(tools.io_input)
    else:
        input_data = request.data

    try:
        data = json.loads(request.data)
    except Exception as e:
        msg = tools.message({"error": {"code": -32700, "message": "invalid json"}})
        return tools.response_error(msg)
    try:
        valid = CheckRequestKeys(data=data)
    except Exception as e:
        msg = tools.message({"error": {"code": -32600, "message": f"json keys error;{request_format}"}})
        return tools.response_error(msg)
    if data["method"] not in ["tools/list", "tools/call", "server/discover"]:
        msg = tools.message({"error": {"code": -32601, "message": "unknow method; possibles: tools/list | tools/call | server/discover   "}})
        return tools.response_error(msg)
    try:
        valid = CheckRequestParams(data=data)
    except Exception as e:
        msg = tools.message({"error": {"code": -32602, "message": f"json arguments error;{request_format}"}})
        return tools.response_error(msg)


    print("data received:", data) #  TODO ; DEBUG TEST
#    tools.check_args(XX)
#    response = tools.gen_response(XX)
#    return Response(response, status)
    return Response("")


if __name__ == "__main__":
    global STDIO_MODE

    try:
        if len(sys.argv) > 1 and argv[1] == "stdio":
            STDIO_MODE = True
            while 1:
                post_exchange()
        else:
            app.run(host=HOST, port=PORT)
    except Exception as e:
        print(f"server crashed with error : {e}", file=sys.stderr)



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

