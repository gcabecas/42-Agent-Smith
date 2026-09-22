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

    model: dict[str, Any] = dict()
    methods: dict[str, Any]
    response: Callable[..., Response | None] = placeholder
    response_error: Callable[..., Response | None] = placeholder

    ids: int = 0
    queue: dict[int, str] = dict()
    queue_mutex: Any = Lock()
    operation_mutex: Any = Lock()

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

            def response(
                msg: str | Generator, *, content: str = "application/json"
            ) -> Response | None:
                return Response(msg, content_type=content)

            def response_error(
                msg: str | Generator, error: int
            ) -> Response | None:
                return Response(
                    msg, status=error, content_type="application/json"
                )

        else:

            def response(
                msg: str | Generator, *, content: str = "application/json"
            ) -> Response | None:
                if isinstance(msg, Generator):
                    for elem in msg:
                        print(elem, file=self.io_output, flush=True)
                else:
                    print(msg, file=self.io_output, flush=True)
                return None

            def response_error(
                msg: str | Generator, error: int
            ) -> Response | None:
                if isinstance(msg, Generator):
                    for elem in msg:
                        print(msg, file=self.io_output, flush=True)
                else:
                    print(msg, file=self.io_output, flush=True)
                return None

        self.response = response
        self.response_error = response_error

        return self

    def event(self, msg: str) -> str:
        if self.out_format == "http":
            return f"data: {msg}\n\n"
        return msg

    def message(self, infos: dict[str, Any]) -> str:
        base = {"jsonrpc": "2.0"}
        base.update(infos)
        return json.dumps(base)

    def message_complete(
        self, msg: str, tid: int, error: bool = False
    ) -> None:

        msg_data: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": tid,
            "result": {
                "resultType": "complete",
                "content": [{"type": "text", "text": msg}],
            },
        }
        if error:
            msg_data["result"]["isError"] = True
        msg = self.message(msg_data)
        self.queue_mutex.acquire()
        self.queue.update({tid: msg})
        self.queue_mutex.release()

    def check_func_args(self, func: dict[str, Any]) -> str:
        log = ""
        name = func["name"]
        if name not in self.methods.keys():
            return f"error; unknown fonction used: {name}"
        if func.get("arguments") is None:
            func.update({"arguments": dict()})

        for elem in self.methods[name].keys():
            if elem.startswith("_") and elem.endswith("_optional"):
                continue
            if func["arguments"].get(elem) is None and not self.methods[
                name
            ].get("_" + elem + "_optional"):
                log += f"error; missing argument: {elem}"

        for elem in func["arguments"].keys():
            s_elem = str(elem)
            if self.methods[name].get(s_elem) is None:
                log += f"error; unknown argument used: {s_elem}"
            elif not isinstance(
                func["arguments"][s_elem], self.methods[name][s_elem]
            ):
                log += (
                        f"error; wrong type for {s_elem}; used: "
                        f"{type(func['arguments'][s_elem])}, "
                        f"needed: {self.methods[name][s_elem]}"
                )
        if log:
            log = "[key 'arguments' error. missing or wrong value]\n" + log
        return log

    def tools_list(self) -> Response:
        return Response(self.model)

    def server_discover(self) -> Response:
        return Response("")  # TODO

    def tools_call(
        self, func: dict[str, Any], data: dict[str, Any]
    ) -> Generator[str, None, None]:
        self.queue_mutex.acquire()
        tid = data["id"]
        self.queue_mutex.release()

        if func.get("arguments") and func["arguments"]:
            thread = Thread(
                target=getattr(self, func["name"]),
                args=(tid,),
                kwargs=func["arguments"],
            )
        else:
            thread = Thread(target=getattr(self, func["name"]), args=(tid,))

        if data["params"]["_meta"].get("progressToken") is not None:
            notif_data = {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": data["params"]["_meta"]["progressToken"],
                    "progress": 0,
                    "message": "in progress",
                },
            }
            notif_msg = self.message(notif_data)
        else:
            notif_msg = ""
        thread.start()
        start = time.time()
        while 1:
            time.sleep(0.01)
            if not thread.is_alive():
                self.queue_mutex.acquire()
                rep = self.queue.pop(tid)
                self.queue_mutex.release()
                yield self.event(rep)
                break
            if notif_msg and start + 5 <= time.time():
                start = time.time()
                yield self.event(notif_msg)


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
    def checkmeta(self) -> "RequestParamsBase":
        try:
            if self.meta.get("progressToken"):
                if not isinstance(self.meta["progressToken"], (int, str)):
                    raise ValueError(
                        "wrong type for key 'progressToken' :"
                        " need <int> or <string>"
                    )
            self.meta["io.modelcontextprotocol/protocolVersion"]
            self.meta["io.modelcontextprotocol/clientCapabilities"]
        except Exception as e:
            raise ValueError(
                f'error "{e}" _meta data not correctly set, use strictly:\n'
                '"params": { "_meta": {\n'
                '   "io.modelcontextprotocol/protocolVersion": "2026-07-28",\n'
                '   "io.modelcontextprotocol/clientCapabilities":'
                ' {} # Mandatory Key; Argument ignored by the server\n'
                "}, ... }"
            )
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
