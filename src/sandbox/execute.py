import multiprocessing
import multiprocessing.connection
import os
import resource
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from typing import NamedTuple

from src.common.models import SandboxConfig
from src.sandbox.final_answer import final_answer, FinalAnswer
from src.sandbox.security.builtins import SAFE_BUILTINS
from src.sandbox.security.filesystem import restricted_open
from src.sandbox.security.imports import restricted_import
from src.sandbox.security.network import block_network


def _run_one(code: str, namespace: dict, output_path: str) -> tuple[str, str | None]:
    with (
        open(output_path, "w", buffering=1) as output_file,
        redirect_stdout(output_file),
        redirect_stderr(output_file),
    ):
        try:
            exec(code, namespace)
            return ("ok", None)
        except FinalAnswer as e:
            return ("final_answer", e.value)
        except Exception as e:
            name = type(e).__name__
            return ("error", f"{name}: {e}" if str(e) else name)


def _loop(
    in_queue: multiprocessing.Queue,
    out_queue: multiprocessing.Queue,
    config: SandboxConfig,
    output_path: str,
) -> None:
    memory_bytes = config.max_memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    block_network()

    exec_builtins = dict(SAFE_BUILTINS)
    exec_builtins["__import__"] = partial(restricted_import, config.authorized_imports)
    exec_builtins["open"] = partial(restricted_open, config.allowed_directories)
    exec_builtins["final_answer"] = final_answer

    namespace = {"__builtins__": exec_builtins, "__name__": "__sandbox__"}

    while True:
        code = in_queue.get()
        out_queue.put(_run_one(code, namespace, output_path))


class Result(NamedTuple):
    status: str
    value: str | None
    output: str


class Sandbox:
    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self.in_queue = multiprocessing.Queue()
        self.out_queue = multiprocessing.Queue()

        output_fd, self.output_path = tempfile.mkstemp(prefix="sandbox_output_")
        os.close(output_fd)

        self.process = multiprocessing.Process(
            target=_loop,
            args=(self.in_queue, self.out_queue, config, self.output_path),
        )
        self.process.start()

    def run(self, code: str) -> Result:
        timeout = self.config.max_execution_time_seconds
        self.in_queue.put(code)

        reader, sentinel = self.out_queue._reader, self.process.sentinel
        ready = multiprocessing.connection.wait([reader, sentinel], timeout=timeout)

        if reader in ready:
            status, value = self.out_queue.get()
        elif sentinel in ready:
            status, value = "interrupted", "sandbox process terminated (KeyboardInterrupt or SystemExit)"
        else:
            self._kill()
            status, value = "timeout", f"execution timed out after {timeout}s, output may be partial"

        with open(self.output_path) as output_file:
            return Result(status, value, output_file.read())

    def stop(self) -> None:
        self._kill()
        os.remove(self.output_path)

    def _kill(self) -> None:
        self.process.kill()
        self.process.join()

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *args) -> None:
        self.stop()
