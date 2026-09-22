import argparse
import json
from pathlib import Path

from src.common.models import SandboxConfig, SWEBenchTaskInput
from src.sandbox.cli import repl
from src.sandbox.manual import build_manual
from src.sandbox.mcp_client import McpClient
from src.swebench.testbed import DockerTestbed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="src.swebench")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--python", default="python")
    parser.add_argument("--manual", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task = SWEBenchTaskInput(**json.loads(Path(args.task_file).read_text()))
    print(f"[task] {task.instance_id} ({task.repo})")
    print(f"[image] {task.docker_image}")

    with DockerTestbed(task.docker_image, python=args.python) as testbed:
        if not testbed.has_image():
            print("[image] pulling, this takes a few minutes...")
        testbed.setup(eval_script=task.eval_script)
        print(f"[container] {testbed.container.id[:12]} started")
        print(f"[python] {args.python}")

        client = McpClient(command=testbed.mcp_command())
        print(f"[tools] {', '.join(client.tools)}")

        config = SandboxConfig()
        if args.manual:
            print(build_manual(config, client.specs,
                               client.resources, client.prompts))
        else:
            repl(config, client.tools)

    print("[container] removed")


if __name__ == "__main__":
    main()
