
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
    def get_aftercode_prompt(cls, sandbox_output: str) -> str:
        info = sandbox_output.strip()
        if info:
            out =(
                f"[sandbox output]:(\n{info}\n"
                ")\n\n"
                "If the sandbox output is empty or encounter an error try something different. "
                "If you found a very important information save it with the apropriate tool. "
                "Otherwise continue investigate with tools or end the process with final_answer"
            )
        else:
            out = "Your code was executed, but no print occured"
        return out

    @classmethod
    def get_nocode_prompt(cls) -> str:
        out = "Now you thought about the problem, use tools and eventually code to continue the searchs\n"
        return out

    @classmethod
    def get_first_objective(cls) -> str:
        out = "Find a new current objective to resolve the main one"
        return out

    @classmethod
    def get_first_prompts(cls, repo: str, problem_statement: str,
                                hints_text: list[str], manual: str) -> tuple[str, str]:

        system_prompt = (
            "You are a Software Engineering coding agent"
            "specialised to resolve SWE bench problems. "
            "You need to resolve git repository problems. "
            "You are in a isolated environment, you have only access to a python sandbox and tools usable inside it to acquire data. "
            "Investigate and resolve the given problem "
            "Sandbox tools usage is very important, they give you access to the environemnent you have to debug. "
            "You have to modifie directly files. It is entirely up to you to resolve the problem !\n"
            "You are in a fully automated pipeline, all the pyhton code you give is used in a sandbox and the output is returned by the user. "
            "The user will not read your comments.\n"
            "For security the sandbox is a minimal python environnement, if the code not work, think of trying differents possibilities. "
            "Warning the sandbox is just a test lab not a part of the problem to resolve.\n"
            "Code executed in the sandbox have direct access to MCP-Tools functions, theses functions can interact with the git environemnt.\n"
            "Be smart and wait the result of your message to advise what to do next.\n"

            "So all the code you give, including Mcp-Tools usage need to be in python code block:\n```python\n<CODE>\n```\n"
            "Do not use python code block inside python code block !\n"
            "ONLY YOUR FIRST CODE BLOCK WILL BE EXECUTED !\n"
            "PLEASE WAIT YOUR EXECUTION RESULT TO GO TO THE NEXT STEP !\n"

            "IF YOU ENDED RESOLVING USE THE FOLLOWING FUNCTION :\n"
            "final_answer(git_diff: str)\n"
            "Usage exemple:\n```python\nfinal_answer(exemple_function_to_get_the_git_diff())\n```\n"
            "Here git_diff is the print given by the command git diff, use another tool to get it !"

            "For more you have very important specials functions to manage your memory, helping for investigating, problem researchs and flaw tracking:\n"
            "```python\nset_new_current_objective(objective: str, previous_current_objective_status: str)\n```\n"
            "```python\nadd_main_objective_hint(msg: str)\n```\n"
            "```python\nadd_current_objective_hint(msg: str)\n```\n"
            "Theses functions have automated xml management.\n"
            "THESES FUNCTIONS ASSURE PROMPT SAFETY AND DATA SAVING !\n"
            "Set only large or focused-important current objective\n"
        )
        system_prompt += (
                    "<SANDBOX_RULES>\n" + "USE NEXT TOOLS TO INVESTIGATE !\n"
                    f"{manual}\n</SANDBOX_RULES>\n"
        )
        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            f"Use sandbox tools to access the bugged environement. Use tools to modifie directly files if needed. "
            "It is entirely up to you to resolve the problem !\n"
            "You need to resolve the following problem statement:\n"
            f"{problem_statement}\n"
            "</MAIN_OBJECTIVE>\n"
        )
        if hints_text:
            user_prompt += f"<MAIN_OBJECTIVE_HINT>\n{hints_text}\n</MAIN_OBJECTIVE_HINT>\n"
        return (system_prompt, user_prompt)


class NewSWETaskInput(BaseModel):
    data: SWEBenchTaskInput


class SWEAgent(Agent):

    sandbox: Sandbox
    mcp_tools: dict[str, Any]

    def sandbox_term(self, code: str) -> tuple[str, str]:

#        status, value, output = self.sandbox.run(code + "\n")
#        return (output, False)

        lines = code.split("\n")
        while lines and lines[-1].strip() == "":
            lines.pop()
        result = ""
        final = ""
        for line in lines:
            status, value, output = self.sandbox.run(line)
            result += f"{line}\n{output}\n"
            if status != "ok":
                result += f"[{status}] {value}\n"
                if status == "final_answer":
                    final = value
                break

        self.sandbox.stop()
        self.sandbox = Sandbox(SandboxConfig(), tools=self.mcp_tools)
        return (result, final)

    def create_prompt(self) -> str:
        if self.exec_result:
            out = SWEBasePrompts.get_aftercode_prompt(self.exec_result)
        else:
            out = SWEBasePrompts.get_nocode_prompt()
        return out

    def check_solution(self) -> tuple[bool, str]:
        return (True, "no error")

def create_mbpp_agent(client_command: str, task: SWEBenchTaskInput,
                      *, output: str = "swebench_solution.json",
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

    sandbox = Sandbox(SandboxConfig(), tools=client.tools)
    agent = SWEAgent(
        task_id=task.instance_id, benchmark="swebench",
        system_prompt=system_prompt, output_path=output,
        llmapi=llmapi,
        mcp_tools=client.tools,
        sandbox=sandbox
    )
    return agent


def main(*args: Any, **kwargs: Any) -> None:

    with open(kwargs.pop("task_file"), "r") as file:
        mbpp_data = json.load(file)
    task = NewSWETaskInput(data=mbpp_data).data

    with DockerTestbed(task.docker_image, python="python") as testbed:
        if not testbed.has_image():
            print("[image] pulling, this takes a few minutes...")
        testbed.setup(eval_script=task.eval_script)
        print(f"[container] {testbed.container.id[:12]} started")
        try:
            agent = create_mbpp_agent(testbed.mcp_command(), task, **kwargs)
            check = True
            while check:
                check = agent.next_step()
            agent.create_output()
        except Exception:
            raise
        finally:
            try:
                agent.sandbox.stop()
            except Exception:
                pass
    print("[container] removed")
