
import subprocess
from typing import Any
import json
from pydantic import BaseModel, Field
import pexpect

from src.agent.agent import Agent
from src.agent.helpers import Log, LlmApi
from src.agent.memoryprompt import MemoryPrompt
from src.common.models import SandboxConfig, SWEBenchTaskInput
from src.sandbox.execute import Sandbox
from src.sandbox.manual import build_manual
from src.sandbox.mcp_client import McpClient

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
    def get_first_prompts(cls, function_definition: str, task_definition: str, test_imports: list[str],
            test_list: list[str], manual: str) -> tuple[str, str]:
        system_prompt = (
            "You are a python coding agent "
            "specialised to resolve Mostly Basic Python Problems (MBPP).\n"
            "You are in a fully automated pipeline, all the code you give is used in a sandbox.\n"
            "Code executed in the sandbox have direct access to MCP-Tools functions for specials needs.\n"
            "Use snippet:\n```python\n<code>\n```\n"
            "It is entirely up to you to resolve the problem.\n"
            "If you find the solution and the tests pass; use the following function with the solution code as string in argument:\n"
            "```python\nfinal_answer(code: str)\n```\n"
        )
        system_prompt += "<SANDBOX_RULES>\n" + manual
        if test_imports:
            system_prompt += f"\nFollowing modules are already imported in the environement: {test_imports}"
        system_prompt += "\n</SANDBOX_RULES>\n"

        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            "You need to create a python function:\n"
            f"Function definition: {function_definition}\n"
            f"Description: {task_definition}\n"
        )
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

    max_input_tokens: int = 6000
    max_output_tokens: int = 1500
    max_steps: int = 10
    timeout: float = 120  # TODO

    test_list: list[str]

    def get_instruction_prompt(self) -> None:

        out = (
            "<INSTRUCTIONS>\n"
            "<OUTPUT_FORMAT>\n"
            "A short line of affirmative thought and a single python code snippet :\n"
            "<thoughts>\n"
            "```python\n<code>\n```>\n"
            "</OUTPUT_FORMAT>\n\n"
        )
        if MemoryPrompt.tries:
            if len(MemoryPrompt.tries) > 1:
                msg_attempts = "LAST_ATTEMPT and FAILED_ATTEMPTS"
            else:
                msg_attempts = "LAST_ATTEMPT"
            out += (
                # "<PRIMAL_DIRECTIVE>\n"
                "Only if ALL ASSERTS PASSED in the LAST_ATTEMPT, use final_answer tool with the LAST_ATTEMPT solution code as argument.\n\n"
                # "</PRIMAL_DIRECTIVE>\n"
                f"Otherwise, use the information in {msg_attempts} to accomplish the following tasks:\n"
                "\t1: create the function of the MAIN_OBJECTIVE.\n"
                "\t2: test assertions of the MAIN_OBJECTIVE.\n"
                "\tRules:\n"
                "\t\tuse one single snippet.\n"
                "\t\tfollow the SANDBOX_RULES restrictions.\n"
                "\t\tif the sandbox encounters an ERROR due to restrictions violation, use a different way to create the function.\n"
                "\t\tif the assertions fail (ERROR), try a new solution to resolve the MAIN_PROBLEM.\n"
                "\t\tdo not use final_answer"
            )
        else:
            out += (
                "You have to:\n"
                "\t1: create the function of the MAIN_OBJECTIVE.\n"
                "\t2: test assertions of the MAIN_OBJECTIVE.\n"
                "\tRules:\n"
                "\t\tuse one single snippet.\n"
                "\t\tfollow the SANDBOX_RULES restrictions.\n"
            )
        out += (
            "</INSTRUCTIONS>\n"
        )
     #   if MemoryPrompt.tries:
     #       out += (
     #           "If the LAST_ATTEMPT is without error, "
     #           "use final_answer tool with the solution code string as argument.\n"
     #           "Otherwise; Follow instructions."
     #       )
     #   else:
        out += "Follow INSTRUCTIONS, and use OUTPUT_FORMAT"
        return out

    def sandbox_term(self, code: str) -> tuple[str, str]:

        sandbox = Sandbox(self.sandbox_config)
        try:
            status, value, output = sandbox.run(code + "\n")
            outputs = ""
            for i, elem in enumerate(outputs.split("\n"), 1):
                outputs += f"{i}: {elem}\n"
            outputs = code
            if output:
                outputs += f"\n[STDOUT]:\n{output}"

            match status:
                case "final_answer":
                    if not value:
                        Log.print("[final_answer without value !!!]")
                    return (output, value)
                case "ok":
                    if "assert" in code:
                        outputs += "\n[ALL ASSERTS PASSED]"
                    return (outputs, "")
                case _:
                    outputs += f"\n[ERROR]\n{value}\n[/ERROR]"
                    return (outputs, "")
        except Exception:
            raise
        finally:
            sandbox.stop()

    def check_solution(self) -> tuple[bool, str]:

        asserts = ""
        for elem in self.test_list:
            asserts += f"\n\n{elem}"

        code = f"{self.imports}\n\n{self.solution}\n\n{asserts}"
        read = self.sandbox_term(code)
        if "[error]" in read:
            return (False, read)
        return (True, "no error")


def create_mbpp_agent(task_file: str, output: str = "mbpp_solution.json",
                      providers_file: str = "config/mbpp_providers.json",
                      provider_url: str = "", model_name: str = "") -> MBPPAgent:

    with open(task_file, "r") as file:
        mbpp_data = json.load(file)
    task = NewMBPPTaskInput(data=mbpp_data).data
    client = McpClient("uv run python mcp_tools_mbpp.py")
    config = SandboxConfig()
    manual = build_manual(config, client.specs, client.resources, client.prompts)

    pr = MBPPBasePrompts.get_first_prompts(
        task.function_definition,
        task.task_definition, task.test_imports,
        task.test_list,
        manual
    )
    system_prompt, user_prompt = pr
    MemoryPrompt.init(system_prompt, user_prompt)
    llmapi = LlmApi(providers_file, provider_url, model_name)

    agent = MBPPAgent(
        task_id=str(task.task_id), benchmark="mbpp",
        system_prompt=system_prompt, output_path=output,
        test_list=task.test_list,
        llmapi=llmapi,
        imports="\n".join(f"import {imp}" for imp in task.test_imports),

        mcp_tools=client.tools,
        sandbox_config=SandboxConfig()
    )
    MemoryPrompt.add_message(agent.get_instruction_prompt())
    return agent


def main(*, task_file: str, output: str = "mbpp_solution.json",
                      providers_file: str = "config/mbpp_providers.json",
                      provider_url: str = "", model_name: str = "") -> None:

    """ MBPP Agent.
        Args:
            task_file: mbpp task file
            output: output file name
            providers_file: json file of providers with llms and keys api names
            provider_url: default provider to use (need model_name)
            model_name: default model to use (need provider_url)

    """

    agent = create_mbpp_agent(
                            task_file, output, providers_file,
                            provider_url, model_name)
    check = True
    while check:
        check = agent.next_step()
    agent.create_output()
