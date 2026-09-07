
import sys
import json
import time
from typing import Any, Literal, Optional, Callable, Generator
from flask import Response
from io import TextIOWrapper
from threading import Thread, Lock
from pydantic import BaseModel, model_validator, ConfigDict, Field


def placeholder(*args, **kwargs) -> None:
    pass

class McpToolsCore(BaseModel):

    out_format: str
    in_format: str
    io_output: Any = sys.stdout
    io_error: Any = sys.stderr
    io_input: Any = sys.stdin

    model: str = ""
    methods: dict[str, Any]
    response: Callable[..., Response | None] = placeholder
    response_error: Callable[..., Response | None] = placeholder

    ids: int = 0
    queue: dict[int, str] = dict()
    queue_mutex: Any = Lock()

    @model_validator(mode="after")
    def checks_after(self) -> "McpToolsCore":
        if not isinstance(self.io_output, TextIOWrapper):
            raise ValueError(f"{self.io_output} not valid TextIOWrapper")
        if not isinstance(self.io_error, TextIOWrapper):
            raise ValueError(f"{self.io_error} not valid TextIOWrapper")

        if self.out_format not in ["http", "stdio"]:
            raise ValueError("out_format invalid, possible : http | stdio")
        if self.in_format not in ["http", "stdio"]:
            raise ValueError("in_format invalid, possible : http | stdio")

        if self.out_format == "http":
            def response(msg: str) -> Response | None:
                return Response(msg)
            def response_error(msg: str, error: int) -> Response | None:
                return Response(msg, status=error)
        else:
            def response(msg: str) -> Response | None:
                print(msg, file=self.io_output)
                return None
            def response_error(msg: str, error: int) -> Response | None:
                print(f"error occured:", msg, file=self.io_error)
                return None
        self.response = response
        self.response_error = response_error

        return self
    
    def message(self, infos: dict[str, Any]) -> str:
        base = {"jsonrpc": "2.0"}
        base.update(infos)
        return json.dumps(base)

    def check_func_args(self, func: dict[str, Any]) -> str:
        log = ""
        name = func["name"]
        if name not in self.methods.keys():
            return f"error; unknow fonction used: {name}"
        if not func.get("arguments"):
            func.update({"arguments": dict()})

        for elem in self.methods[name].keys():
            if elem.startswith("_") and elem.endswith("_optional"):
                continue
            if not func["arguments"].get(elem) and not self.methods[name].get("_" + elem + "_optional"):
                log += f"error; missing argument: {elem}"
        
        for elem in func["arguments"].keys():
            s_elem = str(elem)
            if not self.methods[name].get(s_elem):
                log += f"error; unknow argument used: {s_elem}"
            elif not isinstance(func["arguments"][s_elem], self.methods[name][s_elem]):
                log += f"error; wrong type for {s_elem}; used: {type(func['arguments'][s_elem])}, needed: {self.methods[name][s_elem]}"
        return log

    def tools_list(self) -> Response:
        return Response(self.model)

    def server_discover(self) -> Response:
        return Response("") # TODO

    def tools_call(self, func: dict[str, Any], data: dict[str, Any]) -> Generator[str, None, None]:
        self.queue_mutex.acquire()
        self.ids += 1
        tid = self.ids
        self.queue_mutex.release()

        if func.get("arguments") and func["arguments"]:
            thread = Thread(target=getattr(self, func["name"]), args=(tid,), kwargs=func["arguments"])
        else:
            thread = Thread(target=getattr(self, func["name"]), args=(tid,))

        if data.get("progressToken"):
            notif_data = {
                    "jsonrpc": "2.0",
                    "method": "notifications/progress",
                    "params": {
                        "progressToken": data.get("progressToken"),
                        "progress": 0,
                        "message": "in progress"
                    }
            }
            notif_msg = self.message(notif_data)
        else:
            notif_msg = ""
        thread.start()
        while 1:
            time.sleep(0.01)
            start = time.time()
            if not thread.is_alive():
                self.queue_mutex.acquire()
                rep = self.queue.pop(tid)
                self.queue_mutex.release()
                yield rep
                break
            if notif_msg and start + 5 <= time.now():
                yield notif_msg


class RequestJson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jsonrpc: Literal["2.0"]
    id: str | int
    method: str
    params: Optional[Any] = None

class CheckRequestJson(BaseModel):
    data: RequestJson

class RequestParamsBase(BaseModel):
    meta: dict[str, Any] = Field(alias="_meta")

    @model_validator(mode="after")
    def checkmeta(self) -> "Params":
        try:
            n_valid = 2
            if self.meta.get("progressToken"):
                if not isinstance(self.meta["progressToken"], (int, str)):
                    raise ValueError("wrong type for key 'progressToken' : need <int> or <string>")
                n_valid = 3
            if self.meta["io.modelcontextprotocol/protocolVersion"] != "2026-07-28":
                raise ValueError("need key : io.modelcontextprotocol/protocolVersion == 2026-07-28")
            self.meta["io.modelcontextprotocol/clientCapabilities"]
            if len(self.meta.keys()) > n_valid:
               raise ValueError(
                            f"unknow key detected in {self.meta};\n"
                            "only use io.modelcontextprotocol/protocolVersion and io.modelcontextprotocol/clientCapabilities") 
        except Exception as e:
            raise ValueError(
                    f'error "{e}" _meta data not correctly set, use strictly:'
                    '"params": { "_meta": {'
                    '   "io.modelcontextprotocol/protocolVersion": "2026-07-28"',
                    '   "io.modelcontextprotocol/clientCapabilities": {} # Mandatory Key; Argument ignored by the server'
                    '}, ... }')
        return self

class RequestParamsList(RequestParamsBase):
    model_config = ConfigDict(extra="forbid")

class RequestParamsCall(RequestParamsBase):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict[str, Any] = dict()

class CheckRequestParamsList(BaseModel):
    data: RequestParamsList

class CheckRequestParamsCall(BaseModel):
    data: RequestParamsCall

