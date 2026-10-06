from datetime import datetime

from pydantic import BaseModel, Field


class SandboxConfig(BaseModel):
    """Sandbox configuration for student solutions.
    Uses allowlist approach: only imports in authorized_imports are allowed.
    Everything else is blocked by default.
    """
    authorized_imports: list[str] = Field(default_factory=lambda: [
        "math", "math.*",
        "collections", "collections.*",
        "itertools", "re", "json",
        "typing", "typing.*",
        "functools", "operator",
        "heapq", "bisect", "copy",
        "string", "random",
        "datetime", "datetime.*",
        "array", "cmath",
    ])
    allowed_directories: list[str] = Field(default_factory=lambda: [
        "/testbed", "/tmp/agent"
    ])
    max_execution_time_seconds: int = 30
    max_memory_mb: int = 512


class MBPPTaskInput(BaseModel):
    """Input for an MBPP task, provided by the moulinette.

    Your agent receives this as the task definition to solve.
    """
    task_id: int
    task_definition: str
    function_definition: str
    test_imports: list[str] = Field(default_factory=list)
    test_list: list[str] = Field(default_factory=list)


class SWEBenchTaskInput(BaseModel):
    """Input for a SWE-bench task, provided by the moulinette.

    Your agent receives this and must produce a git patch that fixes
    the issue.
    """
    instance_id: str
    problem_statement: str
    docker_image: str
    eval_script: str
    hints_text: str = ""
    repo: str = ""


class StepMetrics(BaseModel):
    """Metrics for a single agent step.

    Each step corresponds to one LLM generate then sandbox execute cycle.
    Empty strings are acceptable where a field does not apply.
    """
    step: int
    input_tokens: int
    output_tokens: int
    request_time_ms: float
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat())
    api_url: str = ""
    model_name: str = ""
    llm_output: str = ""
    sandbox_input: str = ""
    sandbox_output: str = ""
    retries: int = 0


class SolutionOutput(BaseModel):
    """Output from student solution, required format for evaluation.

    This is the JSON structure the agent writes to solution.json.
    """
    task_id: str
    benchmark: str
    success: bool
    solution: str
    iterations: int
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_time_seconds: float
    steps: list[StepMetrics] = Field(default_factory=list)
    system_prompt: str = ""
    error: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat())
