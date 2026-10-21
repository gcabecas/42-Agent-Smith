
from pydantic import BaseModel, Field
import sys
from typing import Any, Optional
from datetime import datetime

from src.sandbox.execute import Sandbox
from src.common.models import SandboxConfig
from src.agent.stepmetrics import StepMetrics
from src.agent.memoryprompt import MemoryPrompt
from src.agent.helpers import Log, LlmApi


NDEBUG = 0  # TODO debug variable



class SolutionOutput(BaseModel):
    """Output from student solution, required format for evaluation.
    This is the JSON structure your agent must produce and write to solution.
    json.
    The moulinette validates this against task correctness and metrics limits.
    """
    task_id: str = Field(
        description="Task identifier (MBPP task_id a string, or SWE-bench instance_id)")
    benchmark: str = Field(description="Benchmark type: 'mbpp' or  swebench'")

    success: bool = Field(
        default=False, description="Whether the agent believes i solved the task")
    solution: str = Field(
        default="", description="For MBPP: the Python function code For SWE-bench: the git patch (diff)")
    iterations: int = Field(
        default=0, description="Number of agent loop iteration used")
    total_requests: int = Field(
        default=0, description="Total number of LLM AP requests made (including retries)")

    total_input_tokens: int = Field(
        default=0, description="Sum of input_token across all steps")
    total_output_tokens: int = Field(
        default=0, description="Sum of output_token across all steps")

    total_time_seconds: float = Field(
        default=0, description="Wall-clock time fro agent start to finish")
    steps: list[StepMetrics] = Field(
        default_factory=list, description="Per step metrics, one entry per agent iteration")
    system_prompt: str = Field(
        description="Full system prompt sen to the LLM (for provenance checking)")
    error: Optional[str] = Field(
        default="", description="Error message i the agent failed (None if successful)")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(
    ), description="ISO 8601 timestamp of when the solution was produced")


class Agent(SolutionOutput):
    model_config = {"arbitrary_types_allowed": True}

    output_path: str = Field(pattern=r".*\.json$")

    llmapi: LlmApi
    sandbox_config: SandboxConfig
    mcp_tools: dict[str, Any]

    exec_result: str = ""
    start: datetime = datetime.now()
    imports: str = ""
    executed: bool = False
    previous_sandbox_output: str = ""


    def set_step_data(self, new: StepMetrics, resp: dict[str, str | int], start: datetime) -> None:

        new.llm_input = resp["llm_input"]
        new.llm_output = resp["llm_output"]
        new.input_tokens = resp["input_tokens"]
        new.output_tokens = resp["output_tokens"]
        new.api_url = resp["api_url"]
        new.model_name = resp["model_name"]
        new.retries = resp["retries"]
        self.total_input_tokens += resp["input_tokens"]
        self.total_output_tokens += resp["output_tokens"]
        time = datetime.now() - start
        new.request_time_ms = time.total_seconds() * 1000

        msg = f"[(ID {self.task_id}) STEP FINISHED ]------------------------"
        for key, elem in new.__dict__.items():
            msg += f"||{key}|=|{elem}||\n"
        for elem in MemoryPrompt.messages:
            msg += f"{str(elem)}\n"
        msg += f"tot in: {self.total_input_tokens} || tot out: {self.total_output_tokens}\n\n"
        Log.print(msg)

    def create_prompt(self, flag: str) -> str:

        out = ""
        if self.executed:
            out += (
                f"<{flag}>\n{self.exec_result}\n"
                f"</{flag}>\n\n"
            )
        out += self.get_instruction_prompt()

        return out

    def next_step(self) -> bool:

        self.iterations += 1
        self.executed = False
        start = datetime.now()
        new = StepMetrics(step=len(self.steps) + 1)
        self.steps.append(new)

        DEBUG = False
        #DEBUG = False
        global NDEBUG
        NDEBUG += 1
        if DEBUG:  # TODO debug if
            resp = {  # TODO
                    "llm_input": "current",
                    "llm_output": """```python
print("helo")
set_new_current_objective("Investigate the error and find a solution to resolve the problem", "in progress")
print("bye")
```""",
                "input_tokens": 0,
                "output_tokens": 0,
                "api_url": "no url",
                "model_name": "no model",
                "retries": 0
            }
        else:
            if MemoryPrompt.swe_mode:
                Log.print(f"step is now: {MemoryPrompt.current_step}")
                if MemoryPrompt.current_step in ["clean memory", "hypothesis", "rule_on"]:
                    resp = self.llmapi.response(MemoryPrompt.messages, 0.1)
                else:
                    resp = self.llmapi.response(MemoryPrompt.messages, 0.1)
            else:
                resp = self.llmapi.response(MemoryPrompt.messages)

        MemoryPrompt.add_message(resp["llm_output"], "assistant")
        codes = MemoryPrompt.get_message_codes()

        self.exec_result = ""
        is_code = [elem for elem in codes if elem.strip()]
        if is_code:
            self.executed = True
            for i, code in enumerate(codes, 1):
                if self.imports:
                    code = f"{self.imports}\n{code}"
                read, final = self.sandbox_term(code)
                if not read.replace("''", "", 1).strip():
                    read = "'[Code executed, but no print occured]'"
                elif len(read) > 5000:
                    if not "test" in resp["llm_output"]:
                        err_msg = (
                            "\n<WARNING>\n"
                            "SANDBOX_OUTPUT truncated at 5000 characters.\n"
                            "Retrieve the remainder using available tools if possible and truly necessary.\n"
                            "</WARNING>"
                        )
                        read = read[:5000] + err_msg
                if len(codes) > 1:
                    new.sandbox_input += f"[codeblock: {i}]\n{code}\n"
                    new.sandbox_output += f"[codeblock: {i}]\n{read}\n"
                else:
                    new.sandbox_input = code
                    new.sandbox_output = read

                if final:
                    self.solution = final
                    self.set_step_data(new, resp, start)
                    self.success = True
                    return False
            self.exec_result = new.sandbox_output

        self.set_step_data(new, resp, start)
        if MemoryPrompt.swe_mode:
            if MemoryPrompt.current_step == "clean memory":
                MemoryPrompt.simple_save_missing_info(new.llm_output)

            loop = MemoryPrompt.check_step_loop()
            if loop:
                self.executed = False
            else:
                MemoryPrompt.compress_user_msg(self.previous_sandbox_output, self.executed)
                self.previous_sandbox_output = new.sandbox_output
                
            #if len(self.steps) >= 28:
            #    MemoryPrompt.last_step = True
            #if MemoryPrompt.current_step == "investigate":
            #    if len(self.steps) <= 15:
            #        if len(MemoryPrompt.step_memory) >= 10:
            #            MemoryPrompt.simple_go_next_step()
            #    elif len(self.steps) <= 23:
            #        if len(MemoryPrompt.step_memory) >= 9:
            #            MemoryPrompt.simple_go_next_step()
            #    elif len(self.steps) == 28:
            #        MemoryPrompt.simple_go_next_step()
            #    else:
            #        if len(MemoryPrompt.step_memory) >= 3:
            #            MemoryPrompt.simple_go_next_step()

            MemoryPrompt.apply_go_next_step(self.testbed)
            prompt = self.create_prompt("SANDBOX_OUTPUT")
            MemoryPrompt.add_message(prompt)
        else:
            MemoryPrompt.save_try(new.sandbox_output)
            MemoryPrompt.compress_user_msg(self.previous_sandbox_output, self.executed)
            self.previous_sandbox_output = new.sandbox_output
            MemoryPrompt.compress_memory()
            prompt = self.create_prompt("LAST_ATTEMPT")
            MemoryPrompt.add_message(prompt)

        msg = ""
        if self.total_input_tokens >= self.max_input_tokens:
            msg += f"Input tokens out of limits: {self.max_input_tokens}\n"
        if self.total_output_tokens >= self.max_output_tokens:
            msg += f"Output tokens out of limits: {self.max_output_tokens}\n"
        if len(self.steps) >= self.max_steps:
            msg += f"Steps out of limits: {self.max_steps}\n"
        if msg:
            self.error = msg
            return False

        if DEBUG and NDEBUG == 10:  # TODO
            return False
        else:
            return True

    def create_output(self) -> None:

        time = datetime.now() - self.start
        total_time = time.total_seconds()
        output = SolutionOutput(

            task_id=self.task_id,
            benchmark=self.benchmark,

            success=self.success,
            solution=self.solution,
            iterations=self.iterations,
            total_requests=self.llmapi.requests,

            total_input_tokens=self.total_input_tokens,
            total_output_tokens=self.total_output_tokens,

            total_time_seconds=total_time,
            steps=self.steps,
            system_prompt=self.system_prompt,
            timestamp=self.timestamp
        )

        success, error = self.check_solution()
        output.error += error
        output.success = (
                output.success and
                success
        )
        if output.success:
            Log.print(f"[{output.benchmark.upper()}_SUCCESS_END]")
        else:
            Log.print(f"[{output.benchmark.upper()}_FAILURE_END]")

        try:
            with open(self.output_path, "w") as f_open:
                f_open.write(f"\n{output.model_dump_json(indent=2)}")
        except Exception as e:
            raise ValueError(f"can't write file {self.output_path}: {e}")
