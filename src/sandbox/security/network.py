import socket
from typing import Any


class BlockedSocket(socket.socket):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise OSError("network access is disabled in the sandbox")


def block_network() -> None:
    setattr(socket, "socket", BlockedSocket)
