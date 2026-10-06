import argparse
import codeop
import sys

from src.common.models import SandboxConfig
from src.sandbox.config import load_config
from src.sandbox.execute import Sandbox
from src.sandbox.manual import build_manual
from src.sandbox.mcp_client import McpClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sandbox")
    parser.add_argument("config", nargs="?", type=load_config,
                        default=SandboxConfig())
    parser.add_argument("--mcp-stdio")
    parser.add_argument("--mcp-server")
    parser.add_argument("--manual", action="store_true")
    return parser.parse_args()


def _is_complete(source: str) -> bool:
    try:
        return codeop.compile_command(source, symbol="single") is not None
    except SyntaxError:
        return True


def read_entry() -> str | None:
    lines: list[str] = []

    while True:
        try:
            lines.append(input("... " if lines else ">>> "))
        except EOFError:
            print()
            return None

        source = "\n".join(lines)
        if _is_complete(source):
            return source


def repl(sandbox: Sandbox) -> None:
    while True:
        code = read_entry()

        if code is None or code.strip() in ("exit", "exit()"):
            break

        status, value, output = sandbox.run(code)
        if output:
            print(output, end="")
        if status != "ok":
            print(f"[{status}] {value}")


def main() -> None:
    args = parse_args()
    if not (args.mcp_stdio or args.mcp_server):
        with Sandbox(args.config) as sandbox:
            return repl(sandbox)
    try:
        client = McpClient(args.mcp_stdio, args.mcp_server)
    except Exception as e:
        sys.exit(f"sandbox: cannot connect to MCP server: {e}")
    if args.manual:
        print(build_manual(args.config, client.specs,
                           client.resources, client.prompts))
    else:
        with Sandbox(args.config, client.tools) as sandbox:
            repl(sandbox)


if __name__ == "__main__":
    main()
