import socket


class BlockedSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise OSError("network access is disabled in the sandbox")


def block_network() -> None:
    socket.socket = BlockedSocket
