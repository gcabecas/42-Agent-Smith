
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

# ============================================================================
# REWORK PRINCIPLES APPLIED (vs your v1):
#
#  1. ONE VOICE: second-person imperative everywhere ("You must..."), no "we",
#     no "it is up to you" (initiative is removed from the model, kept by the
#     pipeline).
#  2. FORCED CHOICE: each step is a numbered decision tree with at most 2-3
#     legal actions, never an open assignment.
#  3. PLAN MICRO-THINKING: every step output starts with ONE fixed line
#     "PLAN: <one line>" then the code block. Short enough to prevent
#     word-drift, long enough to give the model a self-trace.
#  4. TEMPLATES: structured outputs (hypothesis, memo) are fill-in-the-blank
#     skeletons, machine-checkable.
#  5. PER-STEP TOOL VISIBILITY: the pipeline injects the manual of ONLY the
#     tools legal in the current step (see TOOLS_FOR_STEP). Forbidden tools are
#     not just prohibited: they are not shown at all in that step.
#  6. RE-INJECTED PROHIBITIONS: critical rules are repeated inside each step
#     prompt (instruction decay after long context).
#  7. ACTIVE KNOWN_INFO: knowledge blocks always end with what the next
#     message MUST do with that knowledge.
#  8. PIPELINE-VERIFIED EXITS: each step has a machine-checkable exit
#     condition (marked PIPELINE CHECK) - the pipeline validates transitions,
#     it never trusts the model's self-assessment.
#  9. HISTORY RULES (pipeline side): never rewrite old assistant messages;
#     keep code->result pairs atomic; compress only at phase transitions by
#     appending a summary, never by editing.
# 10. LOOP GUARD (pipeline side): hash each emitted code block. If a
#     near-duplicate is detected, return the synthetic observation:
#     "[LOOP DETECTED] You already ran this. Result was: <...>. You must try a
#     different action."
# ============================================================================


class SWEBasePrompts:

    # ---------------------------------------------------------------------------
    # Per-step tool whitelist. The pipeline renders the manual for ONLY these
    # tools into the step prompt. A tool not listed here must not be mentioned
    # in that step's prompt at all.
    # ---------------------------------------------------------------------------
    TOOLS_FOR_STEP = {
        "investigate": ["search", "read_file", "list_dir", "run_python"],
        "modifie": ["read_file", "write_file", "edit_file", "run_python"],
        "test": ["run_python"],
        "clean memory": [],
        "hypothesis": ["propose_hypothesis"],
        "rule_on": ["run_python", "rule_on_hypothesis", "final_answer"],
    }

    @classmethod
    def _step_manual(cls, manual: str) -> str:
        # PIPELINE: filter the manual down to TOOLS_FOR_STEP[current_step]
        # before injection. `manual` here is expected to be pre-filtered.
        return manual

    @classmethod
    def _render_known_info(cls) -> str:
        hints = getattr(MemoryPrompt, "hints", None) or []
        if not hints:
            return ""
        block = "<KNOWN_INFO>\n"
        block += "Facts already established by previous attempts:\n"
        for h in hints:
            block += f"- {h}\n"
        # ACTIVE USE: the info comes with an obligation, not decoration.
        block += (
            "Your next message MUST either USE one of these facts "
            "(name it in your PLAN line) or explicitly contradict one "
            "with new evidence.\n"
            "</KNOWN_INFO>\n\n"
        )
        return block

    @classmethod
    def _render_hypotheses(cls) -> str:
        hyps = getattr(MemoryPrompt, "hypothesis", None) or []
        if not hyps:
            return ""
        block = "<HYPOTHESES>\n"
        block += "Already-proposed hypotheses (do NOT re-propose these):\n"
        for h in hyps:
            block += f"- {h['hyp']}\n"
        block += "</HYPOTHESES>\n\n"
        return block

    @classmethod
    def _plan_rule(cls) -> str:
        return (
            "OUTPUT FORMAT (mandatory, every message):\n"
            "PLAN: <one single line: what this code will do and what you expect to learn>\n"
            "```python\n<CODE>\n```\n"
            "No other text. No comments inside the code. One code block = one Python snippet.\n"
        )

    @classmethod
    def get_first_prompts(cls, repo: str, problem_statement: str,
                          hints_text: list[str], manual: str) -> tuple[str, str]:

        system_prompt = (
            "You are a software engineering agent. You resolve SWE-bench "
            "problems inside a git repository.\n\n"

            "You act ONLY through a Python sandbox. Every action you take is "
            "one Python code block. The pipeline executes it and returns you "
            "the output. There is no other way to act.\n\n"
            
            "OUTPUT FORMAT (mandatory, every message):\n"
            "PLAN: <one single line>\n"
            "```python\n<CODE>\n```\n"
            "Rules:\n"
            "- The PLAN line is one line maximum. No reasoning beyond it.\n"
            "- One code block = one Python snippet = one action.\n"
            "- No comments, no explanations, no text outside this format.\n"
            "- If your code fails, you receive the error as the next "
            "observation. Fix it in the next message.\n\n"

            "The sandbox is your lab. It is separate from the bugged "
            "repository. Use it to inspect and modify the repository through "
            "the tools.\n\n"

            "Test files and test folders are NEVER part of the problem. "
            "Never edit them.\n\n"

            "<SANDBOX_RULES_AND_TOOLS>\n"
            f"{cls._step_manual(manual)}\n"
            "<SPECIAL_TOOLS>\n"
            "You have five special tools that drive the pipeline. The pipeline "
            "decides the current step; you signal inside a step ONLY with "
            "these:\n"
            "```python\n"
            "go_next_step()\n"
            "save_missing_info(msg)\n"
            "propose_hypothesis(files, msg)\n"
            "rule_on_hypothesis(verdict, evidence)\n"
            "final_answer(git_diff)\n"
            "```\n"
            "Usage example:\n"
            "```python\n"
            "final_answer(get_git_diff())  # use a sandbox tool to obtain the diff first\n"
            "```\n"
            "</SPECIAL_TOOLS>\n"
            "</SANDBOX_RULES_AND_TOOLS>\n\n"

            "Follow the current step instruction exactly. Each step tells you "
            "which actions are legal. Doing anything else is a failure."
        )

        user_prompt = (
            "<MAIN_OBJECTIVE>\n"
            "Resolve this problem statement:\n"
            f"<PROBLEM>\n{problem_statement}\n</PROBLEM>\n"
        )
        if hints_text:
            user_prompt += (
                "<HINTS>\n"
                + "\n".join(f"- {h}" for h in hints_text)
                + "\n</HINTS>\n"
            )
        user_prompt += "</MAIN_OBJECTIVE>"

        return (system_prompt, user_prompt)


class NewSWETaskInput(BaseModel):
    data: SWEBenchTaskInput


class SWEAgent(Agent):

    max_input_tokens: int = 300000
    max_output_tokens: int = 10000
    max_steps: int = 30
    timeout: float = 1800

    sandbox_config: SandboxConfig
    mcp_tools: dict[str, Any]
    testbed: DockerTestbed

    # ------------------------------------------------------------------------
    # Message history rules (pipeline side, enforced in code not in prompts):
    # - Never rewrite or delete an existing assistant message.
    # - Keep (assistant code, tool result) pairs atomic in history.
    # - At each phase transition, APPEND a compact summary message
    #   (memo + hypothesis + diff-so-far + last 2 code/result pairs) and
    #   drop older raw turns from the window.
    # ------------------------------------------------------------------------

    def get_instruction_prompt(self) -> str:

        step = MemoryPrompt.current_step

        # Common header: step identity + format reminder (re-injected every
        # message to fight instruction decay).
        out = f"<INSTRUCTION>\nCURRENT STEP: {step.upper()}\n\n"
        out += SWEBasePrompts._render_known_info()

        if step == "investigate":
            out += SWEBasePrompts._render_hypotheses()
            out += (
                "<INVESTIGATE>\n"
                "Goal: know the exact file AND function containing the bug. "
                "Do not modify anything in this step.\n\n"
                "Answer these questions in order. Each question gives you "
                "exactly ONE legal action:\n\n"
                "1. Do you already know the file(s) that likely contain the bug "
                "(from MAIN_OBJECTIVE, HINTS or KNOWN_INFO)?\n"
                "   - NO  -> your only action: run a repository search for the "
                "symbols/keywords of the problem. Then stop and wait.\n"
                "   - YES -> go to 2.\n"
                "2. Have you read that file since learning it was suspicious?\n"
                "   - NO  -> your only action: read the WHOLE file. Then stop "
                "and wait.\n"
                "   - YES -> go to 3.\n"
                "3. Can you name the exact function and describe in one line "
                "what it does wrong at runtime?\n"
                "   - NO  -> your only action: read the next most suspicious "
                "file, or run a minimal reproduction script. Then stop.\n"
                "   - YES -> stop investigating. Call propose_hypothesis with "
                "this exact message template:\n"
                '       propose_hypothesis(files=["<file1>", ...], msg=(\n'
                '           "file: <file>\\n"\n'
                '           "function: <function>\\n"\n'
                '           "root cause: <one sentence>\\n"\n'
                '           "fix sketch: <max 6 lines of code>\\n"\n'
                "       ))\n\n"
                "FORBIDDEN in this step: final_answer, go_next_step, "
                "modifying any file, running the test suite.\n"
                "</INVESTIGATE>\n"
            )
            # PIPELINE CHECK before accepting transition out of investigate:
            # the hypothesis msg contains a non-empty 'file:' AND 'function:'.
            # If not: re-prompt once with "Your hypothesis skeleton is
            # incomplete: <missing field>."

        elif step == "modifie":
            out += (
                "<MODIFY>\n"
                f"HYPOTHESIS:\n{MemoryPrompt.hypothesis[-1]['hyp']}\n\n"
                "Goal: make exactly the change described in the hypothesis. "
                "Nothing more, nothing less.\n\n"
                "Answer in order. Each question gives you ONE legal action:\n\n"
                "1. Is the file containing the function currently loaded in "
                "your context (content you have seen this attempt or in "
                "KNOWN_INFO)?\n"
                "   - NO  -> your only action: read the file. Then stop.\n"
                "   - YES -> go to 2.\n"
                "2. Write the minimal edit implementing the hypothesis. "
                "Edit ONLY the file(s) named in the hypothesis.\n"
                "   Your code must: locate the exact lines, apply the change, "
                "print the modified section so you can verify it.\n"
                "   Then stop and wait for the result.\n"
                "3. The edit is applied and the printed section is correct.\n"
                "   -> your only action: call go_next_step().\n\n"
                "FORBIDDEN in this step: final_answer, running the test suite, "
                "editing files not named in the hypothesis.\n"
                "</MODIFY>\n"
            )
            # PIPELINE CHECK before accepting transition out of modify:
            # `git diff` is non-empty. If empty: re-prompt with
            # "git diff is empty. No modification was recorded."

        elif step == "test":
            out += (
                "<TEST>\n"
                f"HYPOTHESIS:\n{MemoryPrompt.hypothesis[-1]['hyp']}\n\n"
                "Goal: run the tests, judge the result yourself, then end the "
                "process or reject the hypothesis.\n\n"
                "Step 1 - RUN\n"
                "Your only action: run the failing test(s) identified by the "
                "problem statement. Print one line per test with PASS or FAIL. "
                "Then stop and wait for the output.\n\n"
                "Step 2 - JUDGE (next message, after reading the output)\n"
                "First fill this report exactly, nothing else:\n"
                "TEST_REPORT:\n"
                "tests run: <n>\n"
                "passed: <n>   failed: <n>   errors: <n>\n"
                "failing names: <names, or NONE>\n"
                "judgement: PASS or FAIL\n\n"
                "Decision rule (no exception):\n"
                "- FAIL if at least one test printed FAILED or ERROR, or the "
                "run crashed, or zero tests ran.\n"
                "- PASS only if every test you ran passed AND the original "
                "error from the problem statement no longer appears.\n"
                "- Warnings are not failures. Never edit a test file. Never "
                "hide a failure inside try/except.\n\n"
                "Step 3 - ACT\n"
                "- judgement PASS -> call final_answer(get_git_diff()). This "
                "is the ONLY way to succeed. If the diff is empty, do not "
                "call it: your edits did not apply, call "
                'rule_on_hypothesis(verdict="invalid", evidence="git diff is '
                'empty").\n'
                "- judgement FAIL -> do not modify anything more. Call "
                "rule_on_hypothesis(verdict=\"invalid\", evidence=<one "
                "sentence: failing test + observed error>).\n"
                "</TEST>\n"
            )
            # PIPELINE: parse test output deterministically, then inject:
            #   VERDICT: PASS
            # or: VERDICT: FAIL
            #   - test_x (AssertionError: ...)
            #   - test_y (TypeError: ...)
            # Never let the model read raw pytest output.

        elif step == "clean memory":
            out += (
                "<SAVE>\n"
                "You are writing a memo for your NEXT attempt. The repository "
                "will be reset to its original state. Your current edits will "
                "be gone. The next attempt only knows what you write here.\n\n"
                "Hard rules:\n"
                "- Maximum 25 lines.\n"
                "- No tool logs, no raw tracebacks, no copied test output.\n"
                "- Only facts that change the next attempt's decisions.\n"
                "- Fill ALL 5 sections, exactly this structure:\n\n"
                "1) BUG LOCATION\n"
                "   file: <path>\n"
                "   function: <name>\n"
                "   failing expression: <the exact statement that fails>\n\n"
                "2) ROOT CAUSE\n"
                "   <one sentence, the runtime sequence leading to the error. "
                "Do not restate the exception message.>\n\n"
                "3) FIX TO TRY\n"
                "   file: <path>  function: <name>\n"
                "   <code snippet, max 6 lines>\n\n"
                "4) DO NOT RETRY\n"
                "   - <approach> -> <resulting error>\n"
                "   - <approach> -> <resulting error>\n\n"
                "5) CLUES IN THE REPO\n"
                "   - <file>:<line> <the comment/docstring/code line that "
                "points at the intended fix>\n\n"
                "Call save_missing_info(memo) with the memo as msg.\n"
                "</SAVE>\n"
                "</INSTRUCTION>"
            )
            # PIPELINE CHECK: memo contains all 5 section headers and
            # 'file:' non-empty. Otherwise re-prompt once with the missing
            # section names. The memo is then appended to MemoryPrompt.hints
            # and injected as KNOWN_INFO next attempt.

        elif step == "hypothesis":
            # FALLBACK: investigation phase did not exit (loop detected).
            out += SWEBasePrompts._render_hypotheses()
            out += (
                "<PROPOSE_HYPOTHESIS>\n"
                "Investigation is over. You must commit to a hypothesis NOW. "
                "Refusing to commit ends the attempt in failure.\n\n"
                "1. Look at the hypotheses above. Your new hypothesis must be "
                "MATERIALLY DIFFERENT from all of them (different file, "
                "different function, or different root cause).\n"
                "2. Choose the single most probable unexplored candidate.\n"
                "3. Call propose_hypothesis with the skeleton template:\n"
                '   propose_hypothesis(files=["<file>"], msg=(\n'
                '       "file: <file>\\n"\n'
                '       "function: <function>\\n"\n'
                '       "root cause: <one sentence>\\n"\n'
                '       "fix sketch: <max 6 lines>\\n"\n'
                "   ))\n"
                "</PROPOSE_HYPOTHESIS>\n"
            )
            # PIPELINE CHECK: new hypothesis differs from every existing one
            # (string similarity below threshold). If too similar: re-prompt
            # with "This hypothesis is a duplicate of #<n>. Name a different
            # file or function."

        elif step == "rule_on":
            # FALLBACK: test phase did not exit (loop detected).
            out += (
                "<RULE_ON_HYPOTHESIS>\n"
                f'Hypothesis under judgment: "{MemoryPrompt.hypothesis[-1]["hyp"]}"\n\n'
                "You must deliver a verdict NOW. Silence ends the attempt in "
                "failure.\n\n"
                "1. Weigh only the evidence in KNOWN_INFO, the hypothesis "
                "above, and the last test results.\n"
                "2. Call rule_on_hypothesis with exactly one of:\n"
                '   - verdict="valid", evidence=<one sentence: the test that '
                "now passes and why it proves the fix>\n"
                '   - verdict="invalid", evidence=<one sentence: the failing '
                "test and what it proves about the hypothesis>\n"
                "</RULE_ON_HYPOTHESIS>\n"
            )
            # PIPELINE CHECK: verdict in {"valid", "invalid"} and evidence
            # non-empty. If verdict="valid": transition to test to confirm
            # with final_answer. If "invalid": transition to clean memory,
            # then a new attempt with the updated KNOWN_INFO.

        else:
            raise ValueError(f"impossible current_step at prompt creation: {step}")

        if step != "clean memory":
            out += (
                "\nOne tool call per message, then wait for its result.\n"
                "OUTPUT FORMAT TO USE:\n"
                "PLAN: <one affirmative single thinking line>\n"
                "```python\n<code>\n```\n"
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

