
import subprocess
from typing import Any
import json
from pydantic import BaseModel, Field

from src.agent.agent import Agent
from src.agent.helpers import Log, LlmApi, MemoryPrompt


""" MBPP
Implement an agent CLI interface
# 1. Dump a task
cd moulinette
uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json
# 2. Run your agent
cd ../student
uv run python -m agent_mbpp --task-file ../cache/mbpp_task.json \
--output ../cache/mbpp_solution.json \
--model-name "model/name" --provider-url "https://provider.api/v1"
# 3. Validate solution
cd ../moulinette
uv run moulinette_eval validate mbpp ../cache/mbpp_task.json \
../cache/mbpp_solution.json
"""

class MBPPBasePrompts:

    @classmethod
    def get_aftercode_prompt(cls, sandbox_output: str) -> str:
        out = f"[sandbox result]:\n{sandbox_output}\n[note]: If the code encounter a failure find a new solution !"
        return out

    @classmethod
    def get_nocode_prompt(cls) -> str:
        out = "Now you thought about the problem, use code and eventually tools to continue the searches\n"
        return out

    @classmethod
    def get_first_prompts(cls, function_definition: str, task_definition: str, test_imports: list[str],
                          test_list: list[str]) -> tuple[str, str]:
        system_prompt = (
            "You are a python coding agent "
            "specialised to resolve MBPP problems. "
            "You need to resolve Mostly Basic Python Problems. "
            "Create the function demanded by the user with the associed requirements all in python. "
            "Only code is important the user will not read your comments.\n"
            "You are in a fully automated pipeline, all the code you give is used in a sandbox and the output is returned by the user. "
            "Code executed in the sandbox have direct access to MCP-Tools functions for specials needs.\n"
            "So all the code you give, including Mcp-Tools usage need to be in python code block:\n```python\n<CODE>\n```\n"
            "Do not use python code block inside python code block !\n"
            "FOR END RESOLVING USE THE FOLLOWING FUNCTION WITH THE CODE AS ARGUMENT :\n"
            "```python\nfinal_answer(code: str)\n```\n"
        )
        command = ["uv", "run", "sandbox", "--manual",
                   "--mcp-stdio", "uv run python mcp_tools_mbpp.py"]
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
            f"Description: {task_definition}\n"
            f"Function definition: {function_definition}\n"
        )
        if test_imports:
            user_prompt += "Premade imports of the environement are: {test_imports}\n"
        if test_list:
            user_prompt += f"Python assertion(s) need to pass: {test_list}\n"

        user_prompt += "</MAIN_OBJECTIVE>\n"
        return (system_prompt, user_prompt)


class MBPPTaskInput(BaseModel):
    """Input for MBPP task evaluation."""
    task_id: int

    task_definition: str
    function_definition: str
    test_imports: list[str] = Field(default_factory=list)
    test_list: list[str] = Field(default_factory=list)


class NewMBPPTaskInput(BaseModel):
    data: MBPPTaskInput


class MBPPAgent(Agent):

    test_list: list[str]

    def create_prompt(self) -> str:
        if self.exec_result:
            out = MBPPBasePrompts.get_aftercode_prompt(self.exec_result)
        else:
            out = MBPPBasePrompts.get_nocode_prompt()
        return out

    def check_solution(self) -> tuple[bool, str]:

        asserts = ""
        for elem in self.test_list:
            asserts += f"\n\n{elem}"

        # TODO use arguments in a json file
        command = ["uv", "run", "sandbox", "--mcp-stdio",
                   "uv run python mcp_tools_mbpp.py"]
        code = f"{self.imports}\n\n{self.solution}\n\n{asserts}"
        read = self.sandbox_term(command, code)
        if "[error]" in read:
            return (False, read)
        return (True, "no error")


def create_mbpp_agent(*, task_file: str, output: str = "mbpp_solution.json",
                      providers_file: str = "config/mbpp_providers.json",
                      provider_url: str = "", model_name: str = "") -> MBPPAgent:

    with open(task_file, "r") as file:
        mbpp_data = json.load(file)
    task = NewMBPPTaskInput(data=mbpp_data).data

    pr = MBPPBasePrompts.get_first_prompts(
        task.function_definition,
        task.task_definition, task.test_imports,
        task.test_list)
    system_prompt, user_prompt = pr
    prompt = MemoryPrompt(system_prompt, user_prompt)
    llmapi = LlmApi(providers_file, provider_url, model_name)

    agent = MBPPAgent(
        task_id=str(task.task_id), benchmark="mbpp",
        system_prompt=system_prompt, output_path=output,
        test_list=task.test_list,
        llmapi=llmapi,
        prompt=prompt,
        imports="\n".join(f"import {imp}" for imp in task.test_imports)
    )
    return agent


def main(*args: Any, **kwargs: Any) -> None:
    agent = create_mbpp_agent(**kwargs)
    check = True
    while check:
        check = agent.next_step()
    agent.create_output()