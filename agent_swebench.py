import argparse
import sys
import time
from pathlib import Path

from src.common.limits import Budget, Limits
from src.common.models import (SolutionOutput, StepMetrics,
                               SWEBenchTaskInput)
from src.sandbox.execute import Result, Sandbox
from src.swebench.session import SweBenchSession, load_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent_swebench")
    parser.add_argument("--task-file", required=True,
                        help="SWE-bench task JSON dumped by the moulinette")
    parser.add_argument("--output", required=True,
                        help="where to write the solution JSON")
    parser.add_argument("--model-name", required=True,
                        help="model identifier, e.g. 'qwen/qwen3-235b'")
    parser.add_argument("--provider-url", required=True,
                        help="LLM API base URL")
    parser.add_argument("--max-iterations", type=int, default=30,
                        help="hard limit on agent loop iterations")
    parser.add_argument("--python", default="python",
                        help="interpreter used by the MCP server in the "
                             "container")
    return parser.parse_args()


def build_system_prompt(task: SWEBenchTaskInput, manual: str) -> str:
    return (
        f"{manual}\n\n"
        f"You are fixing an issue in the {task.repo} repository, "
        f"already checked out at /testbed.\n\n"
        f"<issue>\n{task.problem_statement}\n</issue>\n\n"
        f"Explore the code with the tools, apply a minimal fix, check it "
        f"with run_tests(), then submit with final_answer(get_patch())."
    )


def run_agent_stub(sandbox: Sandbox, system_prompt: str, budget: Budget,
                   args: argparse.Namespace) -> tuple[
                       Result, list[StepMetrics], str | None]:
    steps: list[StepMetrics] = []
    # mets la boucle argentique ici, elle tourne tant que
    # budget.stop_reason(steps) vaut None
    return (sandbox.run("final_answer(get_patch())"), steps,
            budget.stop_reason(steps))


def build_solution(task: SWEBenchTaskInput, system_prompt: str,
                   result: Result | None, steps: list[StepMetrics],
                   seconds: float, error: str | None) -> SolutionOutput:
    solved = result is not None and result.status == "final_answer"
    patch = result.value or "" if solved and result is not None else ""
    return SolutionOutput(
        task_id=task.instance_id,
        benchmark="swebench",
        success=error is None and bool(patch),
        solution=patch,
        iterations=len(steps),
        total_requests=sum(1 + step.retries for step in steps),
        total_input_tokens=sum(step.input_tokens for step in steps),
        total_output_tokens=sum(step.output_tokens for step in steps),
        total_time_seconds=round(seconds, 3),
        steps=steps,
        system_prompt=system_prompt,
        error=error,
    )


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    try:
        task = load_task(args.task_file)
        output.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        sys.exit(f"agent_swebench: {type(e).__name__}: {e}")

    started = time.monotonic()
    budget = Budget(Limits(iterations=args.max_iterations,
                           input_tokens=300_000,
                           output_tokens=10_000,
                           seconds=900.0))
    system_prompt = ""
    result: Result | None = None
    steps: list[StepMetrics] = []
    error: str | None = None
    try:
        with SweBenchSession(task, args.python) as session:
            print(f"[task] {task.instance_id} ({task.repo})")
            sandbox = session.start()
            system_prompt = build_system_prompt(task, session.manual)
            done, steps, stopped = run_agent_stub(
                sandbox, system_prompt, budget, args)
            result = done
            if done.status != "final_answer":
                error = stopped or f"agent ended with status {done.status}"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print(f"agent_swebench: {error}", file=sys.stderr)

    solution = build_solution(task, system_prompt, result, steps,
                              time.monotonic() - started, error)
    output.write_text(solution.model_dump_json(indent=2))
    print(f"[solution] {output} success={solution.success}")

    if error is not None:
        sys.exit(1)


if __name__ == "__main__":
    main()
