
import subprocess
from typing import Any
import json
from pydantic import BaseModel, Field

from src.agent.agent import Agent
from src.agent.helpers import Log, LlmApi, MemoryPrompt


""" SWE
Implement an agent CLI interface
# 1. Dump a task
cd moulinette
uv run moulinette_eval dump swebench --output ../cache/swebench_task.json
# 2. Run your agent
cd ../student
uv run python -m agent_swebench --task-file ../cache/swebench_task.json \
--output ../cache/swebench_solution.json \
--model-name "model/name" --provider-url "https://provider.api/v1"
# 3. Validate solution
cd ../moulinette
uv run moulinette_eval validate swebench ../cache/swebench_task.json \
../cache/swebench_solution.json
"""


class SWEBasePrompts:

    @classmethod
    def get_aftercode_prompt(cls, sandbox_output: str) -> str:
        out = f"[sandbox result]:\n{sandbox_output}\n[note]: If the code encounter a failure find a new solution !"
        return out

    @classmethod
    def get_nocode_prompt(cls) -> str:
        out = "Now you thought about the problem, use tools and eventually code to continue the searches\n"
        return out

    @classmethod
    def get_first_objective(cls) -> str:
        out = "Find a new current objective or resolve the main one directly"
        return out

    @classmethod
    def get_first_prompts(cls, repo: str, problem_statement: str,
                                hints_text: list[str]) -> tuple[str, str]:

        system_prompt = (
            "You are a python coding agent "
            "specialised to resolve MBPP problems. "
            "You need to resolve Mostly Basic Python Problems. "
            "Create the function demanded by the user with the associed requirements all in python. "
            "Only code is important the user will not read your comments.\n"
            "You are in a fully automated pipeline, all the code you give is used in a sandbox and the output is returned by the user. "
            "For security the sandbox is a minimal python environnement, if the code not work, think of trying differents possibilities. "
            "Code executed in the sandbox have direct access to MCP-Tools functions for specials needs.\n"
            "So all the code you give, including Mcp-Tools usage need to be in python code block:\n```python\n<CODE>\n```\n"
            "Do not use python code block inside python code block !\n"
            "FOR END RESOLVING USE THE FOLLOWING FUNCTION WITH THE CODE AS ARGUMENT :\n"
            "```python\nfinal_answer(code: str)\n```\n"
            "For more you have important specials functions to manage your memory, helping for problem researchs and flaw tracking:\n"
            "```python\nset_new_current_objective(self, msg: str, old_objective_status: str)\n```\n"
            "```python\nadd_main_objective_hint(msg: str)\n```\n"
            "```python\nadd_current_objective_hint(msg: str)\n```\n"
            "Theses functions have automated XML management\n"
        )
        command = ["uv", "run", "sandbox", "--manual",
                   "--mcp-stdio", "uv run python mcp_tools_swebench.py"]
        result = subprocess.run(
            command,
            cwd=".",
            capture_output=True,
            text=True,
        )
        system_prompt += "<SANDBOX_RULES>\n" + \
            str(result.stdout) + "\n</SANDBOX_RULES>\n"

        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            f"You need to create a python function :"
            f"Description: {problem_statement}\n"
            "</MAIN_OBJECTIVE>\n"
        )
        if hints_text:
            user_prompt += f"<MAIN_OBJECTIVE_HINT>\n{hints_text}\n</MAIN_OBJECTIVE_HINT>\n"

        user_prompt += f"<CURRENT_OBJECTIVE>{cls.get_first_objective()}</CURRENT_OBJECTIVE>"
        return (system_prompt, user_prompt)


class SWEBenchTaskInput(BaseModel):
    """Input for a SWE-bench task, provided by the moulinette.
    Your agent receives this and must produce a git patch that fixes
    the issue.
    """
    instance_id: str = Field(
        ..., description="SWE-bench instance identifier (e.g., 'sympy__sympy-23534')")
    problem_statement: str = Field(
        ..., description="The GitHub issue description, what needs to be fixed")
    docker_image: str = Field(
        ..., description="Full Docker image name to pull (e.g., 'swebench/sweb.eval.x86_64. sympy_1776_sympy-23534:latest')")
    eval_script: str = Field(
        ..., description="Bash script to run inside the container to evaluate the patch")
    hints_text: str = Field(
        default="", description="Optional hints about the issue (may be empty)")
    repo: str = Field(
        default="", description="Repository name (e.g., 'sympy/sympy')")


class NewSWETaskInput(BaseModel):
    data: SWEBenchTaskInput


class SWEAgent(Agent):

    def create_prompt(self) -> str:
        if self.exec_result:
            out = SWEBasePrompts.get_aftercode_prompt(self.exec_result)
        else:
            out = SWEBasePrompts.get_nocode_prompt()
        return out

    def check_solution(self) -> tuple[bool, str]:

        # TODO use arguments in a json file
#        command = ["uv", "run", "sandbox", "--mcp-server",
#                   "http://127.0.0.1:8042"]
#        code = f"{self.imports}\n\n{self.solution}\n\n{asserts}"
#        read = self.sandbox_term(command, code)
        read = "error"
    
        if "[error]" in read:
            return (False, read)
        return (True, "no error")


def create_mbpp_agent(*, task_file: str, output: str = "swebench_solution.json",
                      providers_file: str = "config/swe_providers.json",
                      provider_url: str = "", model_name: str = ""
                      ) -> tuple[SWEAgent, SWEBenchTaskInput]:

    with open(task_file, "r") as file:
        mbpp_data = json.load(file)
    task = NewSWETaskInput(data=mbpp_data).data

    pr = SWEBasePrompts.get_first_prompts(
        task.repo,
        task.problem_statement,
        task.hints_text
        # eval_script ??
    )
    system_prompt, user_prompt = pr
    prompt = MemoryPrompt(system_prompt, user_prompt, SWEBasePrompts.get_first_objective())
    llmapi = LlmApi(providers_file, provider_url, model_name)

    command = ["uv", "run", "sandbox", "--mcp-server",
                "http://127.0.0.1:8042"]
    agent = SWEAgent(
        task_id=task.instance_id, benchmark="swebench",
        system_prompt=system_prompt, output_path=output,
        llmapi=llmapi,
        prompt=prompt,
        sandbox_cmd=command
    )
    return (agent, task)


from src.sandbox.mcp_client import McpClient
from src.swebench.testbed import DockerTestbed


def main(*args: Any, **kwargs: Any) -> None:

    agent, task = create_mbpp_agent(**kwargs)
    print(f"[task] {task.instance_id} ({task.repo})")
    print(f"[image] {task.docker_image}")

    with DockerTestbed(task.docker_image, {"8042/tcp": ("127.0.0.1", 8042)}) as testbed:
        if not testbed.has_image():
            print("[image] pulling, this takes a few minutes...")
        testbed.setup(eval_script=task.eval_script)
        print(f"[container] {testbed.container.id[:12]} started")
        client = McpClient(command=testbed.mcp_command())
        print(f"[tools] {', '.join(client.tools)}")

        check = True
        while check:
            check = agent.next_step()
            check = False
        agent.create_output()

    print("[container] removed")


if __name__ == "__main__":
    main()