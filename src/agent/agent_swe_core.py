
import subprocess
from typing import Any
import json
from pydantic import BaseModel, Field

from src.common.models import SandboxConfig, SWEBenchTaskInput
from src.sandbox.execute import Sandbox
from src.agent.agent import Agent
from src.agent.helpers import LlmApi, MemoryPrompt, Log
from src.swebench.server_docker import server_docker
from src.sandbox.mcp_client import McpClient
from src.sandbox.manual import build_manual
from src.sandbox.cli import read_entry_from_python
from src.swebench.testbed import DockerTestbed

import random


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
            "You are a software engineering coding agent "
            "specialised to resolve SWE bench problems.\n"
            "You need to resolve a problem inside a git repository containing bugged files.\n"

            "You are in a isolated git repository environment, you have only access to a python sandbox and tools usable inside it to acquire data and take action.\n"
            "Sandbox tools usage is very important, they are python functions usable inside the sandbox, they give you access to the environment you have to debug.\n"
            "The user will not read comments, use mainly python code with tools provided !\n"
            "It is entirely up to you to resolve the problem ! You have to modifie directly files.\n"
            "You are in a fully automated pipeline, all the pyhton code you give is used in the sandbox and the output is returned by the user,"
            " if the code not work, think of trying differents possibilities.\n"
            "The sandbox is just a small lab not a part of the bugged environment and not a part of problem to resolve.\n"
            "So all the code you give, need to be in python code block:\n```python\n<CODE>\n```\n"
            "Do not use python code block inside python code block !\n"
            "Try to use several tools at once to speed up the process.\n"
            "USE A MAXIMUM OF 5 TOOLS AT A TIME !\n"

        )
        system_prompt += (
                f"<SANDBOX_RULES_AND_TOOLS>\n{manual}\n"
                "<SPECIAL_TOOL>\n"
                "For more you have a very important special tool to manage the monitoring:\n"
                "go_next_step()\n"
                "exemple usage: ```python\ngo_next_step()\n```\n"
                "follow the instruction to use it correctly\n"
                "<SPECIAL_TOOL>\n"
                "</SANDBOX_RULES_AND_TOOLS>"
        )
        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            "You need to resolve the following problem statement:\n"
            f"<PROBLEM>\n{problem_statement}</PROBLEM>\n"
            "It is entirely up to you to resolve the problem inside the git repository environment accessed with mcp-tools,"
            " including applie modifications (with available python tools) !\n"
            "</MAIN_OBJECTIVE>\n"
        )
        if hints_text:
            user_prompt += f"<MAIN_OBJECTIVE_HINT>\n{hints_text}\n</MAIN_OBJECTIVE_HINT>\n"
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
                    if not value:
                        Log.print("[final_answer without value !!!]")
                    return (output, value)
                case "ok":
                    return (output, "")
                case _:
                    return (f"<ERROR>\n[STDOUT]: {output}\n[ERROR MESSAGE]: {value}\n</ERROR>", "")
        except Exception:
            raise
        finally:
            sandbox.stop()


    def create_prompt(self) -> str:

        out = ""
        anti_repetition_words = [
            # Nouveauté
            "new", "novel", "fresh", "original", "innovative", "inventive",
            "unprecedented", "unseen", "untried", "unexplored", "uncharted",
            "first-of-its-kind", "groundbreaking", "pioneering", "cutting-edge",
            "state-of-the-art",
            # Différence / unicité
            "different", "distinct", "distinctive", "unique", "singular",
            "one-of-a-kind", "unlike", "alternative", "divergent", "unconventional",
            "unorthodox", "atypical", "non-obvious", "unexpected", "surprising",
            "unfamiliar",
            # Variété
            "varied", "diverse", "versatile", "multifaceted", "assorted", "mixed",
            "eclectic", "wide-ranging", "many-sided", "alternating", "rotating",
            # Changement / progression
            "changing", "evolving", "shifting", "progressive", "incremental",
            "adaptive", "dynamic", "transformative", "pivotal", "decisive",
            "game-changing",
            # Créativité
            "creative", "imaginative", "resourceful", "ingenious", "clever", "smart",
            "lateral", "out-of-the-box", "experimental", "exploratory",
            # Information / valeur ajoutée
            "informative", "insightful", "revealing", "enlightening", "illuminating",
            "meaningful", "substantive", "additive", "productive", "fruitful", "useful",
        ]

        if self.executed:
            info = self.exec_result.strip()
            if not info:
                info = "[Your code was executed, but no print occured]"
            out += (
                f"<SANDBOX_OUTPUT>\n{info}\n"
                "</SANDBOX_OUTPUT>\n\n"
            )

        out += (
            "<DIRECTIVE>\n\n"
        )
        if MemoryPrompt.current_step == "get data":
            out += (
                "<INVESTIGATE>\n"
                "You can execute SANDBOX_TOOLS to investigate !\n"
                "We need to investigate before acting.\n"
                "Use only tools to get informations !\n"
                "We need to figure out where is located the bug exactly before acting.\n"
                "What tools usage can give you interestings new hints ?\n"
                "\n"
                "Do not use tool to modifie files or anything, instead use the go_next_step SPECIAL_TOOL\n"
                "Do not use the final_answer tool\n"
                "</INVESTIGATE>\n"
            )
        elif MemoryPrompt.current_step == "modifie":
            out += (
                "<ACT>\n"
                "You can execute SANDBOX_TOOLS to act !\n"
                "Dependingly informations you get.\n"
                "What to do to resolve the problem ?.\n"
                "What file(s) you can change or add to resolve the problem ?\n"
                "\n"
                "Do not use tool to investigate or test, instead use the go_next_step SPECIAL_TOOL\n"
                "Do not use the final_answer tool\n"
                "</ACT>\n"
            )
        elif MemoryPrompt.current_step == "test":
            out += (
                "<TEST>\n"
                "You can execute SANDBOX_TOOLS to test !\n"
                "Use only tools for checking the results."
                "What test(s) can check and valid changes made ?\n"
                "</TEST>\n"
                    
                "<END>\n"
                "Only if tests pass and you resolved the main problem, you can end the process with final_answer(git_diff: str)\n"
                "Usage exemple:\n```python\nfinal_answer(exemple_function_to_get_the_git_diff(...))\n```\n"
                "Here git_diff is the string or print given by the command git diff, use another tool to get it !\n"
                "</END>\n\n"

                "If tests are not concluant use the go_next_step SPECIAL_TOOL\n"
            )
        else:
            out += (
                "You need to define informations usefull to resolve the PROBLEM and missing from KNOWN_INFO. "
                "Use the save_missing_info SPECIAL_TOOL to save theses informations !\n"
                "exemples :\n"
                "```python\n"
                'save_missing_info("the function at ligne <x> in the file exemple.py cause ...")\n'
                "```\n"
                "```python\n"
                'save_missing_info("the error in mainly located in files foo.py and funcs.py ...")\n'
                "```\n"
                "```python\n"
                'save_missing_info("i think the problem can be fixed with ...")\n'
                "```\n"
                "```python\n"
                'save_missing_info("the file file.py was modified, but created a new bug, we need to restore files")\n'
                "```\n"
            )
            MemoryPrompt.current_step = "reset"

        out += (
            "\n</DIRECTIVE\n\n>"
        )
        out += (
            "<INSTRUCTION\n>"
            "Follow the DIRECTIVE"
            "Respond with Python codeblock(s) only, without comments.\n\n"
            "USE A MAXIMUM OF 5 TOOLS !\n"
            "</INSTRUCTION\n>"
        )

        magic1 = random.choice(anti_repetition_words)
        while 1:
            magic2 = random.choice(anti_repetition_words) 
            if magic1 != magic2:
                break
        # out += f"Be {magic1} and {magic2} in your response !\n"

        return out

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
        sandbox_config=SandboxConfig(),
        demand="memorise"
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

