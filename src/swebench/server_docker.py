import argparse
import json
from pathlib import Path

from src.common.models import SandboxConfig, SWEBenchTaskInput
from src.sandbox.cli import repl
from src.sandbox.manual import build_manual
from src.sandbox.mcp_client import McpClient
from src.swebench.testbed import DockerTestbed

from src.sandbox.execute import Sandbox


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="src.swebench")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--python", default="python")
    parser.add_argument("--manual", action="store_true")
    return parser.parse_args()


class server_docker():
    def __init__(self, task: SWEBenchTaskInput, python: str = "python") -> None:
        self.tasks = task
        self.python = python
        self.testbed = DockerTestbed(self.tasks.docker_image, python=self.python)

    def start(self) -> None:
        if not self.testbed.has_image():
            print("[image] pulling, this takes a few minutes...")
        self.testbed.setup(eval_script=self.tasks.eval_script)
        print(f"[container] {self.testbed.container.id[:12]} started")
        print(f"[python] {self.python}")


def main() -> None:

    server = server_docker("swe_task.json", python="python3.10")
    server.start()
    sandbox = Sandbox(SandboxConfig(), tools={})

    # status, value, output = sandbox.run("print('Hello, World!')") # code llm a la place du hello world
    # if output:
    #     print(output, end="")
    # if status != "ok":
    #     print(f"[{status}] {value}")

if __name__ == "__main__":
    main()