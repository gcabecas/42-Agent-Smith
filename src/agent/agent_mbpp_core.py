import json
from pydantic import BaseModel, Field

from src.agent.agent import Agent
from src.agent.helpers import Log, LlmApi
from src.agent.memoryprompt import MemoryPrompt
from src.common.models import SandboxConfig
from src.sandbox.execute import Sandbox
from src.sandbox.manual import build_manual
from src.sandbox.mcp_client import McpClient


class MBPPBasePrompts:
    @classmethod
    def get_first_prompts(
        cls,
        function_definition: str,
        task_definition: str,
        test_imports: list[str],
        test_list: list[str],
        manual: str,
    ) -> tuple[str, str]:
        system_prompt = (
            "You are a python coding agent "
            "specialised to resolve Mostly Basic Python Problems (MBPP).\n"
            "You are in a fully automated pipeline, all the code you give is used in a sandbox.\n"
            "Code executed in the sandbox have direct access to MCP-Tools functions for specials needs.\n"
            "Use snippet:\n```python\n<code>\n```\n"
            "It is entirely up to you to resolve the problem.\n"
        )
        system_prompt += "<SANDBOX_RULES>\n" + manual
        if test_imports:
            system_prompt += f"\nFollowing modules are already imported in the environement: {test_imports}"
        system_prompt += "\n</SANDBOX_RULES>\n"

        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            "You need to create a python function:\n"
            f"Function definition: {function_definition}\n"
            f"DESCRIPTION: {task_definition}\n"
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
    timeout: float = 120
    test_list: list[str]
    state: str = "normal"

    def get_instruction_prompt(self) -> None:

        out = "<INSTRUCTIONS>\n"
        if self.state == "final_answer":
            out += (
                "ALL ASSERTS PASSED !\n"
                "You find the solution and the tests passed.\n"
                "Use final_answer tool with the LAST_ATTEMPT solution code as string argument.\n"
                "```python\nfinal_answer(code: str)\n```\n"
            )
        elif MemoryPrompt.tries:
            if len(MemoryPrompt.tries) > 1:
                msg_attempts = "LAST_ATTEMPT and FAILED_ATTEMPTS"
            else:
                msg_attempts = "LAST_ATTEMPT"
            out += (
                "Create the function of the MAIN_OBJECTIVE, matching its DESCRIPTION.\n"
                "Use one single snippet.\n"
                "Follow the SANDBOX_RULES restrictions.\n"
                f"An ERROR occurred in LAST_ATTEMPT; figure out what failed and propose a different function from {msg_attempts}.\n"
                "If LAST_ATTEMPT encounters an ERROR due to sandbox restrictions violation, use a different way to create the function.\n"
                "If LAST_ATTEMPT assertions fail (ERROR), use a new solution matching the DESCRIPTION.\n"
                "Do not use final_answer.\n"
            )
        else:
            out += (
                "Create the function of the MAIN_OBJECTIVE, matching its DESCRIPTION.\n"
                "Use one single snippet.\n"
                "Follow the SANDBOX_RULES restrictions.\n"
                "Do not use final_answer.\n"
            )
        out += "</INSTRUCTIONS>\n"
        if self.state == "final_answer" or not MemoryPrompt.tries:
            out += "Think a little to comply with INSTRUCTIONS, then give a single python code snippet.\n"
        else:
            out += "Think a little about why LAST_ATTEMPT failed and how to succeed this time by following INSTRUCTIONS. Then give a single python code snippet.\n"
        out += "exemple:\n<thoughts>\n```python\n<code>\n```>"
        return out

    def sandbox_term(self, code: str) -> tuple[str, str]:

        sandbox = Sandbox(self.sandbox_config)
        try:
            for elem in self.test_list:
                if elem not in code:
                    code += f"{elem}\n"
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
                        self.state = "final_answer"
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
        read, _ = self.sandbox_term(code)
        if "[ALL ASSERTS PASSED]" not in read:
            return (False, read)
        return (True, "no error")


def create_mbpp_agent(
    task_file: str,
    output: str = "mbpp_solution.json",
    providers_file: str = "config/mbpp_providers.json",
    provider_url: str = "",
    model_name: str = "",
) -> MBPPAgent:

    with open(task_file, "r") as file:
        mbpp_data = json.load(file)
    task = NewMBPPTaskInput(data=mbpp_data).data
    client = McpClient("uv run python mcp_tools_mbpp.py")
    config = SandboxConfig()
    manual = build_manual(
        config, client.specs, client.resources, client.prompts
    )

    pr = MBPPBasePrompts.get_first_prompts(
        task.function_definition,
        task.task_definition,
        task.test_imports,
        task.test_list,
        manual,
    )
    system_prompt, user_prompt = pr
    MemoryPrompt.init(system_prompt, user_prompt)
    llmapi = LlmApi(providers_file, provider_url, model_name)

    agent = MBPPAgent(
        task_id=str(task.task_id),
        benchmark="mbpp",
        system_prompt=system_prompt,
        output_path=output,
        test_list=task.test_list,
        llmapi=llmapi,
        imports="\n".join(f"import {imp}" for imp in task.test_imports),
        mcp_tools=client.tools,
        sandbox_config=SandboxConfig(),
    )
    MemoryPrompt.add_message(agent.get_instruction_prompt())
    return agent


def main(
    *,
    task_file: str,
    output: str = "mbpp_solution.json",
    providers_file: str = "config/mbpp_providers.json",
    provider_url: str = "",
    model_name: str = "",
) -> None:
    """MBPP Agent.
    Args:
        task_file: mbpp task file
        output: output file name
        providers_file: json file of providers with llms and keys api names
        provider_url: default provider to use (need model_name)
        model_name: default model to use (need provider_url)

    """

    agent = create_mbpp_agent(
        task_file, output, providers_file, provider_url, model_name
    )
    check = True
    while check:
        check = agent.next_step()
    agent.create_output()
