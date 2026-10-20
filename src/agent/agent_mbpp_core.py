
import subprocess
from typing import Any
import json
from pydantic import BaseModel, Field
import pexpect

from src.agent.agent import Agent
from src.agent.helpers import Log, LlmApi
from src.agent.memoryprompt import MemoryPrompt


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
                          test_list: list[str]) -> tuple[str, str]:
        system_prompt = (
            "You are a python coding agent "
            "specialised to resolve MBPP problems.\n"
            "You need to resolve Mostly Basic Python Problems.\n"
            "Create the function demanded by the user with the associed requirements all in python.\n"
            "You are in a fully automated pipeline, all the code you give is used in a sandbox and the output is returned by the user.\n"
            "Code executed in the sandbox have direct access to MCP-Tools functions for specials needs.\n"
            "So all the code you give, including Mcp-Tools usage need to be in python code block:\n```python\n<CODE>\n```\n"
            "You have to use one single python code block.\n"
            "Be smart and wait the result of your message to advise what to do next.\n"
            "Do not use python code block inside python code block !\n"
            "FOR END RESOLVING USE THE FOLLOWING FUNCTION WITH THE CODE AS ARGUMENT :\n"
            "```python\nfinal_answer(code: str)\n```\n"
            "Use final_answer if the code pass tests.\n"
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
            f"You need to create a python function:\n"
            f"Function definition: {function_definition}\n"
            f"Description: {task_definition}\n"
        )
        if test_imports:
            user_prompt += "Modules already imported in the environement are: {test_imports}\n"
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
    sandbox_cmd: list[str]


    def get_instruction_prompt(self) -> None:

        out = ""
        out += (
            "<INSTRUCTIONS>\n"
            "Within the SANDBOX_RULES restrictions\n"
            "You have to:\n"
            "   [1]: create the function of the MAIN_OBJECTIVE.\n"
            "   [2]: test assertions of the MAIN_OBJECTIVE.\n"
            "   [sandbox error]: If the sandbox encounters an error due to restrictions violation, use a different way to create the function (go to step 1 again).\n"
            "   [function error]: If the assertions fail, try a new solution to resolve the MAIN_PROBLEM (go to step 1 again).\n"
            "   [3] If tests of the step (2) pass, use final_answer tool with the solution code string as argument.\n"
            "</INSTRUCTIONS>\n"
            "<OUTPUT_FORMAT>\n"
            "A single line of affirmative thought and a single python code snippet :\n"
            "<thoughts>\n"
            "```python\n<code>\n```>\n"
            "</OUTPUT_FORMAT>\n"
            "Follow instructions."
        )
        return out

    def sandbox_term(self, code: str) -> tuple[str, str]:

        result = ""
        term = pexpect.spawn(self.sandbox_cmd[0],
                             self.sandbox_cmd[1:], encoding="utf-8")
        lines = code.split("\n")
        while lines and lines[-1].strip() == "":
            lines.pop()
        try:
            term.setecho(True)
            term.expect_exact([">>> ", "... "])
            result += term.after
            for line in lines:
                term.sendline(line)
                term.expect_exact(
                    ["\n>>> ", "\n... ", "\n[error] ", "\n[final_answer] ."])
                result += term.before + term.after
                if term.after.startswith("\n[error] "):
                    term.sendline("")
                    term.expect_exact(["\n>>> ", "\n... "])
                    result += term.before
                    break
                if term.after.startswith("\n[final_answer] ."):
                    break
            term.sendline("")
            term.sendline("exit")
        except Exception:
            raise
        finally:
            term.terminate(force=True)
        read = result.replace("\r\n", "\n")

        if read.rstrip().endswith("[final_answer] ."):
            final = read.split("[final_answer] ")[1]
            return (read, final)
        return (read, "")

    def create_prompt(self) -> str:

        out = ""
        if self.executed:
            info = self.exec_result.strip()
            if not info.replace("''", "", 1).strip():
                info = "'[Code executed, but no print occured]'"
            out += (
                f"<SANDBOX_OUTPUT>\n{info}\n"
                "</SANDBOX_OUTPUT>\n\n"
            )
        out += self.get_instruction_prompt()

        return out

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

    pr = MBPPBasePrompts.get_first_prompts(
        task.function_definition,
        task.task_definition, task.test_imports,
        task.test_list)
    system_prompt, user_prompt = pr
    MemoryPrompt.init(system_prompt, user_prompt)
    llmapi = LlmApi(providers_file, provider_url, model_name)

    command = ["uv", "run", "sandbox", "--mcp-stdio",
                "uv run python mcp_tools_mbpp.py"]
    agent = MBPPAgent(
        task_id=str(task.task_id), benchmark="mbpp",
        system_prompt=system_prompt, output_path=output,
        test_list=task.test_list,
        llmapi=llmapi,
        imports="\n".join(f"import {imp}" for imp in task.test_imports),
        sandbox_cmd=command
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
