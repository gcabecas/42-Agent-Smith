import asyncio
import os
import shlex
from functools import partial
from typing import Any, Callable

from mcp import Client, StdioServerParameters


def _unwrap(error: BaseException) -> BaseException:
    inner: tuple[BaseException, ...] = getattr(error, "exceptions", ())
    return _unwrap(inner[0]) if len(inner) == 1 else error


def _server(command: str | None, url: str | None) -> Any:
    if url:
        return url
    program, *args = shlex.split(command or "")
    return StdioServerParameters(command=program, args=args,
                                 env=dict(os.environ))


class McpClient:
    def __init__(self, command: str | None = None,
                 url: str | None = None) -> None:
        self.server = _server(command, url)
        self.specs = self._run(lambda client: client.list_tools()).tools
        self.resources = self._list("resources")
        self.prompts = self._list("prompts")

        self.tools: dict[str, Callable[..., Any]] = {}
        for tool in self.specs:
            params = list(tool.input_schema.get("properties", {}))
            self.tools[tool.name] = partial(self.call, tool.name, params)
        if self.resources:
            self.tools["read_resource"] = self.read_resource
        if self.prompts:
            self.tools["get_prompt"] = self.get_prompt

    def _list(self, kind: str) -> list[Any]:
        try:
            method = f"list_{kind}"
            result = self._run(lambda client: getattr(client, method)())
        except Exception:
            return []
        return list(getattr(result, kind))

    def _run(self, action: Callable[[Client], Any]) -> Any:
        async def connected() -> Any:
            async with Client(self.server) as client:
                return await action(client)
        try:
            return asyncio.run(connected())
        except BaseException as e:
            raise _unwrap(e) from None

    def read_resource(self, uri: str, /) -> str:
        result = self._run(lambda client: client.read_resource(uri))
        return "\n".join(c.text for c in result.contents if hasattr(c, "text"))

    def get_prompt(self, name: str, /, **arguments: str) -> str:
        result = self._run(lambda client: client.get_prompt(name, arguments))
        return "\n".join(m.content.text for m in result.messages
                         if hasattr(m.content, "text"))

    def call(self, name: str, params: list[str], /,
             *args: Any, **kwargs: Any) -> str:
        arguments = dict(zip(params, args)) | kwargs
        result = self._run(lambda client: client.call_tool(name, arguments))
        text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
        if result.is_error:
            raise RuntimeError(text)
        return text
