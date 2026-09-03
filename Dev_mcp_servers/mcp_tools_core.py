
import sys
import json
import time
from typing import Any, Literal, Optional, Callable, Generator
from flask import Response
from io import TextIOWrapper
from threading import Thread, Lock
from pydantic import BaseModel, model_validator


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
            def response_error(msg: str) -> Response | None:
                return Response(msg)
        else:
            def response(msg: str) -> Response | None:
                print(msg, file=self.io_output)
                return None
            def response_error(msg: str) -> Response | None:
                print(f"error occured:", msg, file=self.io_error)
                return None
        self.response = response
        self.response_error = response_error

        return self
    
    def message(self, infos: dict[str, Any]) -> str:
        base = {"jsonrpc": "2.0"}
        base.update(infos)
        return json.dumps(base)

    def check_args(self, func: dict[str, Any]) -> dict[str, Any]:
        log = ""
        return {"test": 0}
#        if func["name"] not in self.methods.keys()
#            tool.response_error("unknow function used", XXX)
        #for name, args in self.methods[func["name"]].items():

    def tools_list(self) -> Response:
        return Response(self.model)

    def server_discover(self) -> Response:
        return Response("") # TODO

    def tools_call(self, func: dict[str, Any]) -> Generator[str, None, None]:
        self.queue_mutex.acquire()
        self.ids += 1
        tid = self.ids
        self.queue_mutex.release()

        if func.get("arguments") and func["arguments"]:
            thread = Thread(target=getattr(self, func["name"]), args=(tid,), kwargs=func["arguments"])
        else:
            thread = Thread(target=getattr(self, func["name"]), args=(tid,))
        
        thread.start()
        while 1:
            time.sleep(0.01)
            if not thread.is_alive():
                self.queue_mutex.acquire()
                rep = self.queue.pop(tid)
                self.queue_mutex.release()
                yield rep
                break
            yield "in progress" # TODO CREATE RESPONSE FUNC

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

class Params(BaseModel):
    name: str = ""
    arguments: dict[str, Any] = dict()
    # reference: dict[str, Any] = dict()
    _meta: dict[str, Any]

    @model_validator(mode="after")
    def checkmeta(self) -> "Params":
        try:
            if self._meta["io.modelcontextprotocol/protocolVersion"] != "2026-07-28":
                raise 
            if not self._meta.get("io.modelcontextprotocol/clientCapabilities"):
                raise
        except Exception:
            raise ValueError(
                    '_meta data not correctly set, use:'
                    '"params": { "_meta": {'
                    '   "io.modelcontextprotocol/protocolVersion": "2026-07-28"',
                    '   "io.modelcontextprotocol/clientCapabilities": {} # Argument ignored by the server'
                    '}, ... }')
        return self

    @model_validator(mode="after")
    def checkfunc(self) -> "Params":
        return self


class CheckParams(BaseModel):
    data: Params


