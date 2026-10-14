
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
    def get_first_prompts(cls, repo: str, problem_statement: str,
                                hints_text: list[str], manual: str) -> tuple[str, str]:

        system_prompt = (
            "You have to use only text, every tools are executed in text python code blocks.\n"

            "You are a software engineering coding agent "
            "specialised to resolve SWE bench problems.\n"
            "You need to resolve a problem inside a git repository containing bugged files.\n"

            "You are in a isolated git repository environment, you have only access to a python sandbox and tools usable inside it to acquire data and take action.\n"
            "Sandbox tools usage is very important, they are python functions usable inside the sandbox, they give you access to the environment you have to debug.\n"
            "Do not write comments or explanations, only code blocks.\n"
            "It is entirely up to you to resolve the problem. You have to modifie directly files.\n"
            "You are in a fully automated pipeline, all the pyhton code you give is used in the sandbox and the output is returned to you,"
            " if the code not work, think of trying differents possibilities.\n"
            "The sandbox is just a small lab not a part of the bugged environment and not a part of problem to resolve.\n"
            "So all the code you give, need to be in python code block:\n```python\n<CODE>\n```\n"
            "One code block = one Python snippet.\n"

        )
        system_prompt += (
                f"<SANDBOX_RULES_AND_TOOLS>\n{manual}\n"
                "<SPECIAL_TOOL>\n"
                "For more you have a very important special tool to manage the monitoring:\n"
                "go_next_step()\n"
                "save_missing_info(msg: str)\n"
                "propose_hypothesis(files: list[str], msg: str)\n"
                "rule_on_hypothesis(verdict: str, evidence: str)\n"
                "final_answer(git_diff: str)\n"
                "exemple of use:\n```python\nfinal_answer(exemple_function_to_get_the_git_diff(...))\n```\n"
                "Here git_diff is the string or print given by the command git diff, use another tool to get it !\n"
                "follow the instruction to use it correctly\n"
                "</SPECIAL_TOOL>\n"
                "</SANDBOX_RULES_AND_TOOLS>"
        )
        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            "You need to resolve the following problem statement:\n"
            f"<PROBLEM>\n{problem_statement}</PROBLEM>\n"
            "It is entirely up to you to resolve the problem inside the git repository environment accessed with mcp-tools,"
            " including applie modifications (with available python tools).\n"
            "</MAIN_OBJECTIVE>\n"
        )
        if hints_text:
            user_prompt += f"<MAIN_OBJECTIVE_HINT>\n{hints_text}\n</MAIN_OBJECTIVE_HINT>\n"

        return (system_prompt, user_prompt)


class NewSWETaskInput(BaseModel):
    data: SWEBenchTaskInput


class SWEAgent(Agent):

    max_input_tokens: int = 300000
    max_output_tokens: int = 10000
    max_steps: int = 30
    timeout: float = 900  # TODO

    sandbox_config: SandboxConfig
    mcp_tools: dict[str, Any]
    testbed: DockerTestbed

    def get_instruction_prompt(self) -> str:

        out = (
            "<INSTRUCTION>\n\n"
        )
        if MemoryPrompt.current_step == "investigate":
            out += (
                "<INVESTIGATE>\n"
                "Execute SANDBOX_TOOLS to investigate.\n"
                "Based on all the current information obtained.\n"
                "You don't have to modifie now, focus on the investigation. "
                "Use only tools to get informations !\n"
                "Figure out where is located the bug exactly. Changements will be made only later.\n"
                "Use tools can give you interestings new hints.\n"
                "Optimise your tool usage and try find very usefull informations.\n"
                "\n"
                "If enough informations are present, use the propose_hypothesis SPECIAL_TOOL.\n"
                "Do not use the final_answer tool.\n"
                "</INVESTIGATE>\n"
            )
        elif MemoryPrompt.current_step == "modifie":
            out += (
                f"HYPOTHESIS : {MemoryPrompt.hypothesis[-1]['hyp']}\n\n"
                "<MODIFIE>\n"
                "Execute SANDBOX_TOOLS to modifie/add.\n"
                "Based on informations getted through INVESTIGATE and KNOWN_DATA. "
                "Resolve the problem directly.\n"
                "Modifie files and eventual folder with available tools.\n"
                "\n"
                "If all the necessary was modified, use the go_next_step SPECIAL_TOOL.\n"
                "Do not use the final_answer tool.\n"
                "</MODIFIE>\n"
            )
        elif MemoryPrompt.current_step == "test":
            out += (
                '<PRIMAL_DIRECTIVE priority="ABSOLUTE">\n'
                "If all tests pass successfully ([OK]) and the main problem is resolved, end the process with final_answer SPECIAL_TOOL\n"
                "</PRIMAL_DIRECTIVE>\n"

                f"\nHYPOTHESIS : {MemoryPrompt.hypothesis[-1]['hyp']}\n\n"
                "<TEST>\n"
                "Execute SANDBOX_TOOLS to test !\n"
                "Use tools for checking the results of previous modifications.\n"
                "Valid or invalid changes made.\n"
                "</TEST>\n"

                "\n<CONTINUE>\n"
                "If tests are unsuccessful or FAIL and the main problem is unresolved use the rule_on_hypothesis SPECIAL_TOOL.\n"
                "</CONTINUE>\n"
            )
        elif MemoryPrompt.current_step == "clean memory":
            out += (
                '<PRIMAL_DIRECTIVE priority="ABSOLUTE">\n'
                "If all TESTS pass successfully ([OK]) and the main problem is resolved, end the process with final_answer SPECIAL_TOOL\n"
                "If TESTS are unsuccessful or FAIL and the main problem is unresolved follow the CONTINUE rule.\n" 
                "</PRIMAL_DIRECTIVE>\n"

                "<SAVE>\n"
                "WARNING: after this step the repository is RESET to its original state. "
                "ALL the modifications you made are DELETED and will not exist anymore. "
                "Only the information saved with save_missing_info is kept for the next attempt.\n"
                "Define informations usefull to resolve the PROBLEM and missing from KNOWN_INFO. "
                "Use the save_missing_info SPECIAL_TOOL to save theses informations !\n"
                "The function save_missing_info accept every string as argument.\n"
                "Possibles argument usage:\n"
                "- New fact about the problem\n"
                "- What to do or not do next\n"
                "- Description\n"
                "- Precised file and line\n\n"
                "Save only informations to solve the problem from scratch, "
                "do not count on your current modifications being there.\n"
                "</SAVE>\n"

                "\nIf no new information, use the go_next_step SPECIAL_TOOL.\n"
                "\nRun every tool calls needed in parallel.\n"
                "</INSTRUCTION>"
            )
        elif MemoryPrompt.current_step == "hypothesis":
            out += (
                "<PROPOSE_HYPOTHESIS>\n"
                "Check already exlored HYPOTHESES and new informations to propose a very new one.\n"
                "For this use SPECIAL_TOOL: propose_hypothesis(cls, files: list[str], msg: str)\n"
                "</PROPOSE_HYPOTHESIS>\n"
            )
        elif MemoryPrompt.current_step == "rule on":
            out += (
                "<RULE_ON_HYPOTHESIS>\n"
                "Review all available information, including new evidence outside KNOWN_INFO, to reassess the following hypothesis and provide a well-supported verdict: "
                f'"{MemoryPrompt.hypothesis[-1]["hyp"]}"\n'
                "For this use SPECIAL_TOOL: rule_on_hypothesis(cls, verdict: str, evidence: str)\n"
                "</RULE_ON_HYPOTHESIS>\n"

                "\n<SUCCESS_END>\n"
                "If all tests pass successfully ([OK]) and the main problem is resolved, end the process with final_answer SPECIAL_TOOL\n"
                "If tests are unsuccessful or FAIL and the main problem is unresolved follow the RULE_ON_HYPOTHESIS rule.\n" 
                "</SUCCESS_END>\n"
            )
        else:
            raise ValueError("impossible current_step at prompt creation")
        if MemoryPrompt.current_step != "clean memory":
            out += (
                "\nUse one only tool and wait for its result.\n"
                "</INSTRUCTION>"
            )

        return out

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
        read, final = self.sandbox_term("run_tests()")
        if "[OK]" in read:
            return (True, "")
        return (False, "no '[OK]' in test script output")

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


def create_mbpp_agent(testbed: DockerTestbed, task: SWEBenchTaskInput,
                      output: str = "swebench_solution.json",
                      providers_file: str = "config/swe_providers.json",
                      provider_url: str = "", model_name: str = ""
                      ) -> SWEAgent:

    client = McpClient(command=testbed.mcp_command())
    config = SandboxConfig()
    manual= build_manual(config, client.specs, client.resources, client.prompts)

    pr = SWEBasePrompts.get_first_prompts(
        task.repo,
        task.problem_statement,
        task.hints_text,
        manual
    )
    system_prompt, user_prompt = pr
    MemoryPrompt.init(system_prompt, user_prompt, True)
    llmapi = LlmApi(providers_file, provider_url, model_name)

    agent = SWEAgent(
        task_id=task.instance_id, benchmark="swebench",
        system_prompt=system_prompt, output_path=output,
        llmapi=llmapi,
        mcp_tools=client.tools,
        sandbox_config=SandboxConfig(),
        testbed=testbed
    )
    MemoryPrompt.add_message(agent.get_instruction_prompt())
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
                            testbed, task, output,
                            providers_file, provider_url, model_name)
        check = True
        while check:
            check = agent.next_step()
        agent.create_output()
    print("[container] removed")

