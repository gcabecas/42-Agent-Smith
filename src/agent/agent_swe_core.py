
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
# Base
            "You are a Software Engineering coding agent"
            "specialised to resolve SWE bench problems. "
            "You need to resolve git repository problems. "
            "The user will not read comments. But tools using strings need to be used properly\n"
            "You are in a isolated environment, you have only access to a python sandbox and tools usable inside it to acquire data. "
            "Sandbox tools usage is very important, they give you access to the environemnent you have to debug. "
            "You have to modifie directly files. It is entirely up to you to resolve the problem !\n"
            "You are in a fully automated pipeline, all the pyhton code you give is used in a sandbox and the output is returned by the user. "
            "The sandbox is a minimal python environnement, if the code not work, think of trying differents possibilities. "
            "The sandbox is just a small lab not a part of the bugged environement and not a part of problem to resolve."
            " Use mainly tools provided by the sandbox !\n"
            "Code executed in the sandbox have direct access to MCP-Tools functions, theses functions can interact with the git environemnt.\n"
# Code Format
            "So all the code you give, including Mcp-Tools usage need to be in python code block:\n```python\n<CODE>\n```\n"
            "Do not use python code block inside python code block !\n"
            "ONLY YOUR FIRST CODE BLOCK WILL BE EXECUTED !\n"
# Base 2
            "IF YOU ENDED RESOLVING (tests passed) USE THE FOLLOWING FUNCTION :\n"
            "final_answer(git_diff: str)\n"
# Mix Base and Code Format exemples
            "Usage exemple:\n```python\nfinal_answer(exemple_function_to_get_the_git_diff(...))\n```\n"
            "Here git_diff is the string or print given by the command git diff, use another tool to get it !"

            "For more you have very important specials functions to manage your memory, helping for investigating, problem researchs and flaw tracking:\n"
            "<memory_tools>\n"
            "```python\nset_new_current_objective(objective: str)\n```\n"
            "```python\nadd_main_objective_hint(msg: str)\n```\n"
            "```python\nadd_current_objective_hint(msg: str)\n```\n"
            "```python\ndelete_hint(source_objective: str, hint_id: int)\n```\n"
            "</memory_tools>\n"
# Base 3
            "THESES FUNCTIONS ASSURE PROMPT SAFETY AND DATA SAVING !\n"
            "<suggestions>\n Set large or focused-important current objective.\n"
            "Dont hesitate to put detailled informations with longs strings when needed using memory tools !\n"
            "<hint_format>\nin <provenance_format> <provenance> | info: <information>'\n"
            "<hint_format>\n"
            "<exemples>\nin file foos.py | info: this file directly concern the error ...\n"
            "in file module.py | info: this file has nothing to do with the bug\n"
            "in file funcs.py | info: i modified this file with ...\n"
            "in repository this repo | i don't find code about a specific problem\n"
            "in _ general | i think the problem is formed because ... \n</exemples>\n"
            "If you broke files think of restoring the git repository (git restore .) with available tools\n"
            "<suggestions>\n"
        )
        system_prompt += (
                    f"<sandbox_rules>\n{manual}\n"
                    "WARNING TOOLS CAN POSSIBILY MODIFIE FILES, ESPECIALY SCRIPTS !\n"
                    "USE THESES PROVIDED TOOLS TO INVESTIGATE !\n"
                    "\n</sandbox_rules>\n"
        )
        user_prompt = (
            "<main_objective>\n"
            "Use sandbox tools to access the bugged environement. Use tools to modifie directly files if needed. "
            "Try to use several tools at once to speed up the process.\n"
            "It is entirely up to you to resolve the problem !\n"
            "Be attentive of fake pists and order of events (file modifications can cause indices to become obsolete)\n"
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
                    if not value:
                        Log.print("[final_answer without value !!!]")
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
                f"<sandbox_output>\n{info}\n"
                "</sandbox_output>\n\n"
            )

        if self.demand == "code":
            out += (
                    "<directive>\nVerify KNOWN_DATA data to respond something very NEW and PROGRESSING !\n"
                    "<resolving_and_progression>\n"
                    "You need to base you on KNOWN_DATA to find news informations never getted, or deduct what data is obselete or misleading.\n"
                    "You can edit or add things in the environement to evolute it (this is what resolve the main problem or cause the obsolescence of certain hints).\n"
                    "summary: get data -> think -> change data -> check -> think -> (invalidation : repeat the process) / (validation : end)\n"
                    "WE ARE IN ACTION PHASE (get data/change data/check/invalidation/validation)"
                    "\n</resolving_and_progression>\n</directive>\n"
            )
            out += ( 
                "<instruction>\n"
                "RESPOND WITH ONE UNIQUE CODEBLOCK\n"
                "You have to execute a sandbox_tool !\n"
                "What to do to reach your current objective or the main objective, in following the directive.\n"
                "What file(s) you can change or add to resolve the problem ? What test can give you interestings new hints ?\n"
                "If you have enought informations/hints maybe modifie or add a file ?\n"
                "<priority>\nDO NOT TAKE AN ACTION THAT DOES NOT PROGRESS THE RESOLUTION. "
                "DO SOMETHING TO CHANGE SOMETHING IN THE ENVIRONMENT OR FIND NEW INFORMATIONS (not in KNOWN_DATA, unless the hint is obselete).\n</priority>\n"
                "If you resolved the main problem only, you can end the process with final_answer\n"
                "</instruction>\n"
            )
        else:
            out += (
                    "<directive>\nVerify KNOWN_DATA data to respond something very NEW and PROGRESSING !\n"
                    "<resolving_and_progression>\n"
                    "You need to base you on KNOWN_DATA to find news informations never getted, or deduct what data is obselete or misleading. "
                    "Also you can make assumption and valid or invalide a previous assumption.\n"
                    "summary: get data -> think -> change data -> check -> think -> (not ok : repeat the process) / (ok : end)\n"
                    "WE ARE IN THINK PHASE !"
                    "\n</resolving_and_progression>\n</directive>\n"
            )
            out += ( 
                "<instruction>\n"
                "RESPOND WITH ONE UNIQUE CODEBLOCK\n"
                "You have to execute a memory_tool !\n"
                "What new information we get about this last test ? Do we have a new objective or the current is more important ?"
                " A previous hint(s) become obsolete and need to be delete ?\n"
                "If you find no important information you can just log what you do, precise why it's was vain or utile \n"
                "<priority>\nIF NOT NEW INFORMATION FOUND, "
                "PRECISE WHAT NEW THING YOU CAN DO NEXT TO PROGRESS !.\n</priority>\n"
                "If you resolved the main problem only, you can end the process with final_answer\n"
                "</instruction>\n"
            )

        magic1 = random.choice(anti_repetition_words)
        while 1:
            magic2 = random.choice(anti_repetition_words) 
            if magic1 != magic2:
                break
        out += f"Be {magic1} and {magic2} in your response !\n"

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

