import json
from pathlib import Path
from typing import Any

from src.common.models import SandboxConfig, SWEBenchTaskInput
from src.sandbox.execute import Sandbox
from src.sandbox.manual import build_manual
from src.sandbox.mcp_client import McpClient
from src.swebench.testbed import DockerTestbed


def load_task(path: str) -> SWEBenchTaskInput:
    return SWEBenchTaskInput(**json.loads(Path(path).read_text()))


class SweBenchSession:
    def __init__(self, task: SWEBenchTaskInput,
                 python: str = "python") -> None:
        self.task = task
        self.config = SandboxConfig()
        self.testbed = DockerTestbed(self.task.docker_image, python=python)
        self.sandbox: Sandbox | None = None
        self.manual = ""

    def start(self) -> Sandbox:
        if not self.testbed.has_image():
            print("[image] pulling, this takes a few minutes...")
        self.testbed.setup(eval_script=self.task.eval_script)
        print(f"[container] {self.testbed.container.id[:12]} started")

        client = McpClient(command=self.testbed.mcp_command())
        print(f"[tools] {', '.join(client.tools)}")

        self.manual = build_manual(self.config, client.specs,
                                   client.resources, client.prompts)
        self.sandbox = Sandbox(self.config, client.tools)
        return self.sandbox

    def close(self) -> None:
        if self.sandbox is not None:
            self.sandbox.stop()
            self.sandbox = None
        self.testbed.close()

    def __enter__(self) -> "SweBenchSession":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
