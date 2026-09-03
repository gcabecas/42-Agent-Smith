import multiprocessing
import resource
import socket
from functools import partial

from src.common.models import SandboxConfig
from src.sandbox.builtins import SAFE_BUILTINS
from src.sandbox.imports import restricted_import
from src.sandbox.filesystem import restricted_open


class _BlockedSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise OSError("network access is disabled in the sandbox")


def _run(code: str, queue: multiprocessing.Queue, config: SandboxConfig) -> None:
    memory_bytes = config.max_memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    socket.socket = _BlockedSocket

    exec_builtins = dict(SAFE_BUILTINS)
    exec_builtins["__import__"] = partial(restricted_import, config.authorized_imports)
    exec_builtins["open"] = partial(restricted_open, config.allowed_directories)

    try:
        exec(code, {"__builtins__": exec_builtins, "__name__": "__sandbox__"})
        queue.put(("ok", None))
    except Exception as e:
        queue.put(("error", str(e)))


def execute(code: str, config: SandboxConfig) -> tuple[str, str | None]:
    queue: multiprocessing.Queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_run, args=(code, queue, config))
    process.start()
    process.join(timeout=config.max_execution_time_seconds)

    if process.is_alive():
        process.kill()
        process.join()
        return ("timeout", None)

    return queue.get()
