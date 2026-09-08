import argparse
import codeop

from src.common.models import SandboxConfig
from src.sandbox.config import load_config
from src.sandbox.execute import Sandbox


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sandbox")
    parser.add_argument("config", nargs="?", type=load_config, default=SandboxConfig())
    parser.add_argument("--mcp-stdio")
    parser.add_argument("--mcp-server")
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


def repl(config: SandboxConfig) -> None:
    with Sandbox(config) as sandbox:
        while True:
            code = read_entry()

            if code is None or code.strip() == "exit":
                break

            status, value, output = sandbox.run(code)
            if output:
                print(output, end="")
            if status != "ok":
                print(f"[{status}] {value}")


def main() -> None:
    args = parse_args()
    repl(args.config)


if __name__ == "__main__":
    main()
