
import subprocess
from typing import Any
import json
from pydantic import BaseModel, Field

from src.common.models import SandboxConfig, SWEBenchTaskInput
from src.sandbox.execute import Sandbox
from src.agent.agent import Agent
from src.agent.helpers import LlmApi, MemoryPrompt
from src.swebench.server_docker import server_docker
from src.sandbox.mcp_client import McpClient
from src.sandbox.manual import build_manual
from src.sandbox.cli import read_entry_from_python
from src.swebench.testbed import DockerTestbed



#class SWEBenchTaskInput(BaseModel):
#    """Input for a SWE-bench task, provided by the moulinette.
#    Your agent receives this and must produce a git patch that fixes
#    the issue.
#    """
#    instance_id: str = Field(
#        ..., description="SWE-bench instance identifier (e.g., 'sympy__sympy-23534')")
#    problem_statement: str = Field(
#        ..., description="The GitHub issue description, what needs to be fixed")
#    docker_image: str = Field(
#        ..., description="Full Docker image name to pull (e.g., 'swebench/sweb.eval.x86_64. sympy_1776_sympy-23534:latest')")
#    eval_script: str = Field(
#        ..., description="Bash script to run inside the container to evaluate the patch")
#    hints_text: str = Field(
#        default="", description="Optional hints about the issue (may be empty)")
#    repo: str = Field(
#        default="", description="Repository name (e.g., 'sympy/sympy')")


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
    def get_first_objective(cls) -> str:
        out = "Find a new current objective to resolve the main one"
        return out

    @classmethod
    def get_first_prompts(cls, repo: str, problem_statement: str,
                                hints_text: list[str], manual: str) -> tuple[str, str]:

        system_prompt = (
# Base
            "You are a Software Engineering coding agent"
            "specialised to resolve SWE bench problems. "
            "You need to resolve git repository problems. "
            "You are in a isolated environment, you have only access to a python sandbox and tools usable inside it to acquire data. "
            "Sandbox tools usage is very important, they give you access to the environemnent you have to debug. "
            "You have to modifie directly files. It is entirely up to you to resolve the problem !\n"
            "You are in a fully automated pipeline, all the pyhton code you give is used in a sandbox and the output is returned by the user. "
            "The user will not read comments.\n"
            "For security the sandbox is a minimal python environnement, if the code not work, think of trying differents possibilities. "
            "The sandbox is just a small lab not a part of the bugged environement and not a part of problem to resolve."
            " Use mainly tools provided by the sandbox !\n"
            "Code executed in the sandbox have direct access to MCP-Tools functions, theses functions can interact with the git environemnt.\n"
            "Be smart and wait the result of your message to advise what to do next.\n"
# Code Format
            "So all the code you give, including Mcp-Tools usage need to be in python code block:\n```python\n<CODE>\n```\n"
            "Do not use python code block inside python code block !\n"
            "ONLY YOUR FIRST CODE BLOCK WILL BE EXECUTED !\n"
# Base 2
            "PLEASE WAIT YOUR EXECUTION RESULT TO GO TO THE NEXT STEP !\n"
            "IF YOU ENDED RESOLVING (tests passed) USE THE FOLLOWING FUNCTION :\n"
            "final_answer(git_diff: str)\n"
# Mix Base and Code Format exemples
            "Usage exemple:\n```python\nfinal_answer(exemple_function_to_get_the_git_diff(...))\n```\n"
            "Here git_diff is the print given by the command git diff, use another tool to get it !"

            "For more you have very important specials functions to manage your memory, helping for investigating, problem researchs and flaw tracking:\n"
            "<memory_tools>\n"
            "```python\nset_new_current_objective(objective: str)\n```\n"
            "```python\nadd_main_objective_hint(msg: str)\n```\n"
            "```python\nadd_current_objective_hint(msg: str)\n```\n"
            "</memory_tools>\n"
# Base 3
            "THESES FUNCTIONS ASSURE PROMPT SAFETY AND DATA SAVING !\n"
            "<suggestions>\n Set large or focused-important current objective.\n"
            "Dont hesitate to put detailled informations with longs strings when needed using memory tools !\n<suggestions>\n"
        )
        system_prompt += (
                    f"<sandbox_rules>\n{manual}\n"
                    "USE THESES PROVIDED TOOLS TO INVESTIGATE !\n"
                    "\n</sandbox_rules>\n"
        )
        user_prompt = (
            "<main_objective>\n"
            f"Use sandbox tools to access the bugged environement. Use tools to modifie directly files if needed. "
            "It is entirely up to you to resolve the problem !\n"
            "You need to resolve the following problem statement:\n"
            f"<problem>\n{problem_statement}</problem>\n"
            "</main_objective>\n"
        )
        if hints_text:
            user_prompt += f"<main_objective_hint>\n{hints_text}\n</main_objective_hint>\n"
        return (system_prompt, user_prompt)


class NewSWETaskInput(BaseModel):
    data: SWEBenchTaskInput


class SWEAgent(Agent):

    sandbox_config: SandboxConfig
    mcp_tools: dict[str, Any]

    def sandbox_term(self, code: str) -> tuple[str, str]:

        sandbox = Sandbox(self.sandbox_config, tools=self.mcp_tools)
        try:
            status, value, output = sandbox.run(code + "\n")
            match status:
                case "final_answer":
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"final_answer value broken : {type(value)} | {value}")
                    return (output, value)
                case "ok":
                    return (output, "")
                case _:
                    return (f"<error>\n[STDOUT]: {output}\n[ERROR MESSAGE]: {value}\n</error>", "")
        except Exception:
            raise
        finally:
            sandbox.stop()


    def create_prompt(self) -> str:

        out = ""
        if self.executed:
            info = self.exec_result.strip()
            if not info:
                info = "[Your code was executed, but no print occured]"
            out += (
                f"<sandbox_output>\n{info}\n"
                "</sandbox_output>\n\n"
            )

        if self.demand == "test":
            out += ( 
                "<instruction>\n"
                "You have to execute a sandbox_tool !\n"
                "In your current objective with knowed hints."
                "What test can give you an interesting new hint ? or what we need change ?\n"
                "</instruction>\n"
            )
            self.demand = "memorise"
        else:
            out += ( 
                "<instruction>\n"
                "You have to execute a memory_tool !\n"
                "What new information we get about this last test ? Do we have a new objective or the current is more important ?\n"
                "</instruction>\n"
            )
            self.demand = "test"

        out += "Or if you resolved the problem only, end the process with final_answer\n"
        out += "be smart, be inventive"
        return out

        temp = (
            f"<sandbox_output>\n{info}\n"
            "</sandbox_output>\n\n"

            "<instruction>\n<important!> If the sandbox output is empty or encounter an error you need to process something new"
            ", detourning or resolving the error ! If 'assistant' responses are repetitive be smart and stop do the same things ! </important!>\n"
            "If you found relevant information or a lead about the problem save it imediately with a memory_tool, data not saved is instantly erased ! "
            "Otherwise continue investigate with sandbox_tools, or find a new objective, \n</instruction>"
        )


    def check_solution(self) -> tuple[bool, str]:
        return (True, "no error")


def create_mbpp_agent(client_command: str, task: SWEBenchTaskInput,
                      output: str = "swebench_solution.json",
                      providers_file: str = "config/swe_providers.json",
                      provider_url: str = "", model_name: str = ""
                      ) -> SWEAgent:

    client = McpClient(command=client_command)
    config = SandboxConfig()
    manual= build_manual(config, client.specs, client.resources, client.prompts)

    pr = SWEBasePrompts.get_first_prompts(
        task.repo,
        task.problem_statement,
        task.hints_text,
        manual
    )
    system_prompt, user_prompt = pr
    MemoryPrompt.init(system_prompt, user_prompt, SWEBasePrompts.get_first_objective())
    llmapi = LlmApi(providers_file, provider_url, model_name)

    agent = SWEAgent(
        task_id=task.instance_id, benchmark="swebench",
        system_prompt=system_prompt, output_path=output,
        llmapi=llmapi,
        mcp_tools=client.tools,
        sandbox_config=SandboxConfig()
    )
    return agent


def main(*,
            task_file: str,
            output: str = "swebench_solution.json",
            providers_file: str = "config/swe_providers.json",
            provider_url: str = "", model_name: str = ""
            ) -> None:

    """ SWE Bench Agent.
        Args:
            task_file: mbpp task file
            output: output file name
            providers_file: json file of providers with llms and keys api names
            provider_url: default provider to use (need model_name)
            model_name: default model to use (need provider_url)

    """

    with open(task_file, "r") as file:
        mbpp_data = json.load(file)
    task = NewSWETaskInput(data=mbpp_data).data

    with DockerTestbed(task.docker_image, python="python") as testbed:
        if not testbed.has_image():
            print("[image] pulling, this takes a few minutes...")
        testbed.setup(eval_script=task.eval_script)
        print(f"[container] {testbed.container.id[:12]} started")
        agent = create_mbpp_agent(
                            testbed.mcp_command(), task, output,
                            providers_file, provider_url, model_name)
        check = True
        while check:
            check = agent.next_step()
        agent.create_output()
    print("[container] removed")
