import json
import subprocess
import sys
from importlib.resources import files as Files
from typing import Any

from src.mcp_server.mcp_tools_core import McpToolsCore


class MBPPTools(McpToolsCore):
    def run_tests(self, tid: int, code: str, test_list: list[str]) -> None:
        source = code + "\n" + "\n".join(test_list) + "\n"
        try:
            result = subprocess.run(
                [sys.executable, "-c", source],
                capture_output=True,
                text=True,
                timeout=30,
            )
            success = result.returncode == 0
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            success, output = False, "Execution timed out after 30 seconds"
        self.message_complete(
            json.dumps({"success": success, "output": output}), tid
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        methods = {"run_tests": {"code": str, "test_list": list}}
        super().__init__(*args, methods=methods, **kwargs)
        json_file = Files(__package__).joinpath("tools_list_mbpp.json")
        self.model = json.loads(json_file.read_text(encoding="utf-8"))
