
import subprocess
from typing import Any
import json
from pydantic import BaseModel, Field

from src.common.models import SandboxConfig, SWEBenchTaskInput
from src.sandbox.execute import Sandbox
from src.sandbox.mcp_client import McpClient
from src.agent.agent import Agent
from src.agent.helpers import LlmApi, Log
from src.agent.memoryprompt import MemoryPrompt
from src.swebench.server_docker import server_docker
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
            "You are a software engineering coding agent "
            "specialised to resolve SWE bench problems.\n"
            "You need to resolve a problem inside a git repository containing bugged files.\n\n"

            # "You have to use only text, every tools are executed in text python code blocks.\n"
            "You are in a isolated git repository environment, you have only access to a python sandbox and tools usable inside it to acquire data and take action.\n"
            "Sandbox tools usage is very important, they are python functions usable inside the sandbox, they give you access to the environment you have to debug.\n"
            "It is entirely up to you to resolve the problem inside the git repository environment accessed with mcp-tools,"
            " including applie modifications (with available python tools).\n"
            "You are in a fully automated pipeline, all the pyhton code you give is used in the sandbox and the output is returned to you,"
            " if the code not work in the sandbox, think of trying differents possibilities.\n"
            "The sandbox is just a small lab not a part of the bugged environment and not a part of problem to resolve.\n"
            "All the code you give, need to be in python code block:\n```python\n<CODE>\n```\n"
            "One code block = one Python snippet.\n"
            "Do not be baited by tests files and folders. They are never part of the problem.\n\n"

        )
        system_prompt += (
                f"<SANDBOX_RULES_AND_TOOLS>\n{manual}\n"
                "<SPECIAL_TOOL>\n"
                "For more you have a very important special tool to manage the monitoring:\n"
                "go_next_step()\n"
                "propose_hypothesis(files: list[str], msg: str)\n"
                "final_answer(git_diff: str)\n"
                "exemple of use:\n```python\nfinal_answer(exemple_function_to_get_the_git_diff(...))\n```\n"
                "Here git_diff is the string or print given by the command git diff, use another tool to get it.\n"
                "Follow the instructions to use them correctly\n"
                "</SPECIAL_TOOL>\n"
                "</SANDBOX_RULES_AND_TOOLS>"
        )
        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            "The following problem statement need to be resolved:\n"
            f"<PROBLEM>\n{problem_statement}</PROBLEM>\n"
        )
        if hints_text:
            user_prompt += f"<MAIN_OBJECTIVE_HINT>\n{hints_text}\n</MAIN_OBJECTIVE_HINT>\n"
        user_prompt += "</MAIN_OBJECTIVE>\n"

        return (system_prompt, user_prompt)


class NewSWETaskInput(BaseModel):
    data: SWEBenchTaskInput


class SWEAgent(Agent):

    max_input_tokens: int = 300000
    max_output_tokens: int = 10000
    max_steps: int = 30
    timeout: float = 900  # TODO

    testbed: DockerTestbed

    def get_instruction_prompt(self) -> str:

        out = (
            "\n<INSTRUCTIONS>\n"
            f"Current step is : {MemoryPrompt.current_step.upper()}\n\n"
        )
        if MemoryPrompt.current_step == "investigate":
            out += (
                "Based on information of : PROBLEM, KNOWN_INFO.\n"
                "Use SANDBOX_TOOLS to get information to resolve the PROBLEM.\n"
                "Search where and what is the cause of the PROBLEM.\n"
                # "Find the full problematic node (the full function(s) of even the full file(s)).\n"
                "Guideline:"
                "\tDepending current information. "
                " Figure out what is the problematic file(s), then the function(s), then the line(s).\n"
                # "Optimise your tool usage; exemple: If reading, don't read just a few lines; read the entire relevant section.\n"
                "Investigate for missing information.\n"
                "Use one only tool and wait for its result.\n"
                # "You don't have to modifie/add or test, focus on the investigation.\n"
                "If the information provided indicates what is the cause of the PROBLEM, or how to resolve the PROBLEM, use the propose_hypothesis SPECIAL_TOOL.\n"
            )
            if MemoryPrompt.hypothesis:
                out += (
                    "propose_hypothesis need arguments never used in previous HYPOTHESES.\n"
                )
            out += "\nDo not use the final_answer tool.\n"
        elif MemoryPrompt.current_step == "modifie":
            out += (
                f"HYPOTHESIS : {MemoryPrompt.hypothesis[-1]}\n"
                 "Based on information of : PROBLEM, HYPOTHESIS, INVESTIGATE_OUTPUT and KNOWN_INFO.\n"
                "You have to do the minimal changes to fully resolve the PROBLEM.\n"
                "Modifie files and eventual folders with available SANDBOX_TOOLS.\n"
                "Use one only tool and wait for its result.\n"
                "You don't have to investigate or test now, focus on the modifications.\n"
                "If the necessary was modified/added to resolve the PROBLEM, use the go_next_step SPECIAL_TOOL.\n"
                "\nDo not use the final_answer tool.\n"
            )
        elif MemoryPrompt.current_step == "test":
            out += (
                f"\nHYPOTHESIS : {MemoryPrompt.hypothesis[-1]}\n"
                "Based on information of : MODIFIE_OUTPUT and PROBLEM.\n"
                "Use SANDBOX_TOOLS to check and test the results of previous modifications.\n"
                "After TEST_OUTPUT. If tests are FAILED and the main problems still, use the go_next_step SPECIAL_TOOL.\n"
                "After TEST_OUTPUT. If all tests pass successfully ([OK]) and the main PROBLEM is resolved, end the process with final_answer SPECIAL_TOOL\n"
                "Use one only tool and wait for its result.\n"
            )
        elif MemoryPrompt.current_step == "clean memory":
            out += (
                f"\nHypothesis explored: {MemoryPrompt.hypothesis[-1]}\n\n"
                "Based on information of : INVESTIGATE_OUTPUT, MODIFIE_OUTPUT, TEST_OUTPUT and PROBLEM.\n"
                "You are writing a memo for your next attempt.\n"
                "The repository will be reset to its original state. Your current edits are gone.\n"
                "The next attempt only knows KNOWN_INFO and what you write here. Nothing else.\n"
                "You need to write a report of this failed process.\n"
                "\nRules:\n"
                "- Maximum 25 lines. Be concise.\n"
                "- NO tool call logs. NO raw tracebacks. NO copied test output.\n"
                "- Only facts that change the next attempt's decisions.\n"
                "- Use the exact structure below, with all 3 sections and eventually the bonus.\n"
                "\n1) SUMMARY\n"
                "   describe what you thinked and why this process failed\n"
                "\n2) BUG LOCATION\n"
                "   files and lines where modifications was made\n"
                "\n3) CLUES IN THE REPO\n"
                "   Importants information to resolve the problem from INVESTIGATE_OUTPUT.\n"
                "   Comments, docstrings, or existing code lines that point at the intended fix.\n"
                "   Include file and lines references.\n"
                "\nbonus) ROOT CAUSE\n"
                "   Only if you think you already know how to fix the PROBLEM,"
                " you can describe fully how the bug can be fixed the next time, precise files lines and the fix.\n"

                "</INSTRUCTIONS>\n"
            )
        elif MemoryPrompt.current_step == "hypothesis":
            out += (
                # "Based on information of : KNOWN_INFO and INVESTIGATE_OUTPUT.\n"
                "Propose a new hypothesis to resolve the PROBLEM.\n"
                "For this; Execute SPECIAL_TOOL: propose_hypothesis(cls, files: list[str], msg: str)\n"
            )
            if MemoryPrompt.hypothesis:
                out += (
                    "Your hypothesis need to be totally new or precise new important details, do not use already explored HYPOTHESES.\n"
                )
        else:
            raise ValueError(f"impossible current_step at prompt creation : {MemoryPrompt.current_step}")
        if MemoryPrompt.current_step != "clean memory":
            out += (
                "</INSTRUCTIONS>\n\n"
                "Think briefly to comply with INSTRUCTIONS, then give a single python code snippet:\n"
                "exemple:\n"
                "<thoughts>\n"
                "```python\n<code>\n```>"
            )

        return out

    def sandbox_term(self, code: str) -> tuple[str, str]:

        sandbox = Sandbox(self.sandbox_config, tools=self.mcp_tools)
        try:
            status, value, output = sandbox.run("\n" + code + "\n")
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

    def check_solution(self) -> tuple[bool, str]:
        read, final = self.sandbox_term("run_tests()")
        if "[OK]" in read:
            return (True, "")
        return (False, "no '[OK]' in test script output")


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

