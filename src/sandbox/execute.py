import multiprocessing
import multiprocessing.connection
import os
import resource
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from multiprocessing.connection import Connection
from typing import Any, Callable, NamedTuple

from src.common.models import SandboxConfig
from src.sandbox.final_answer import final_answer, FinalAnswer
from src.sandbox.security.builtins import SAFE_BUILTINS
from src.sandbox.security.filesystem import restricted_open
from src.sandbox.security.imports import restricted_import
from src.sandbox.security.network import block_network

MAX_OUTPUT_CHARS = 10_000


def _call_tool(name: str, pipe: Connection, /,
               *args: Any, **kwargs: Any) -> Any:
    pipe.send(("tool_call", (name, args, kwargs)))
    ok, payload = pipe.recv()
    if not ok:
        raise RuntimeError(payload)
    return payload


def _compile(code: str) -> Any:
    try:
        return compile(code, "<sandbox>", "single")
    except SyntaxError:
        return compile(code, "<sandbox>", "exec")


def _run_one(code: str, namespace: dict[str, Any],
             output_path: str) -> tuple[str, str | None]:
    with (
        open(output_path, "w", buffering=1) as output_file,
        redirect_stdout(output_file),
        redirect_stderr(output_file),
    ):
        try:
            exec(_compile(code), namespace)
            return ("ok", None)
        except FinalAnswer as e:
            return ("final_answer", e.value)
        except Exception as e:
            name = type(e).__name__
            return ("error", f"{name}: {e}" if str(e) else name)


def _loop(pipe: Connection, config: SandboxConfig,
          output_path: str, tool_names: list[str]) -> None:
    memory_bytes = config.max_memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    block_network()

    exec_builtins = dict(SAFE_BUILTINS)
    exec_builtins["__import__"] = partial(
        restricted_import, config.authorized_imports)
    exec_builtins["open"] = partial(
        restricted_open, config.allowed_directories)
    exec_builtins["final_answer"] = final_answer

    for name in tool_names:
        exec_builtins[name] = partial(_call_tool, name, pipe)

    namespace = {"__builtins__": exec_builtins, "__name__": "__sandbox__"}

    while True:
        code = pipe.recv()
        pipe.send(_run_one(code, namespace, output_path))


class Result(NamedTuple):
    status: str
    value: str | None
    output: str


class Sandbox:
    def __init__(
        self,
        config: SandboxConfig,
        tools: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self.config = config
        self.tools = tools or {}

        output_fd, self.output_path = tempfile.mkstemp(
            prefix="sandbox_output_")
        os.close(output_fd)

        self._start()

    def _start(self) -> None:
        self.pipe, child_pipe = multiprocessing.Pipe()
        self.process = multiprocessing.Process(
            target=_loop,
            args=(child_pipe, self.config, self.output_path,
                  list(self.tools)),
        )
        self.process.start()

    def run(self, code: str) -> Result:
        self.pipe.send(code)
        status, value = self._wait_for_result()

        with open(self.output_path) as output_file:
            output = output_file.read(MAX_OUTPUT_CHARS + 1)
        if len(output) > MAX_OUTPUT_CHARS:
            output = (output[:MAX_OUTPUT_CHARS]
                      + f"\n[output truncated to {MAX_OUTPUT_CHARS} chars]\n")
        return Result(status, value, output)

    def _wait_for_result(self) -> tuple[str, str | None]:
        timeout = self.config.max_execution_time_seconds
        remaining = float(timeout)
        sentinel = self.process.sentinel

        while True:
            started = time.monotonic()
            ready = multiprocessing.connection.wait(
                [self.pipe, sentinel], timeout=remaining)
            remaining -= time.monotonic() - started

            if sentinel in ready:
                self._restart()
                return ("interrupted",
                        "sandbox process terminated (KeyboardInterrupt "
                        "or SystemExit), sandbox restarted, namespace reset")
            elif self.pipe in ready:
                message = self.pipe.recv()
                if message[0] != "tool_call":
                    return (message[0], message[1])
                name, args, kwargs = message[1]
                self.pipe.send(self._invoke_tool(name, args, kwargs))
            else:
                self._restart()
                return ("timeout",
                        f"execution timed out after {timeout}s, output may "
                        "be partial, sandbox restarted, namespace reset")

    def _invoke_tool(self, name: str, args: tuple[Any, ...],
                     kwargs: dict[str, Any]) -> tuple[bool, Any]:
        try:
            return (True, self.tools[name](*args, **kwargs))
        except Exception as e:
            return (False, str(e))

    def stop(self) -> None:
        self._kill()
        os.remove(self.output_path)

    def _kill(self) -> None:
        self.process.kill()
        self.process.join()

    def _restart(self) -> None:
        self._kill()
        self._start()

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
