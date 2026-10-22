#!/usr/bin/env python3
"""Run every task that can be selected by the active exam moulinette."""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import random
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOULINETTE = ROOT / "info/given/moulinette/moulinette"
DEFAULT_RESULTS_ROOT = ROOT / "eval-results"

LIMITS = {
    "mbpp": {
        "iterations": 10,
        "input_tokens": 6_000,
        "output_tokens": 1_500,
        "time_seconds": 120.0,
    },
    "swebench": {
        "iterations": 30,
        "input_tokens": 300_000,
        "output_tokens": 10_000,
        "time_seconds": 900.0,
    },
}

EXAM_SELECTION = {
    "mbpp": {"draws": 5, "required": 4},
    "swebench": {"draws": 3, "required": 2},
}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    elapsed_seconds: float
    timed_out: bool = False


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_logged(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    timeout: float | None = None,
) -> CommandResult:
    """Run a command in its own process group and enforce a hard timeout."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {shlex.join(command)}\n\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            elapsed = time.monotonic() - started
            log.write(f"\n[TIMEOUT] killed after {elapsed:.1f}s\n")
            return CommandResult(124, elapsed, True)
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise

    return CommandResult(
        process.returncode,
        time.monotonic() - started,
        False,
    )


def mbpp_dataset_path(moulinette_dir: Path) -> Path:
    return moulinette_dir / "moulinette/mbpp/data/sanitized_tasks.json"


def load_mbpp_dataset(moulinette_dir: Path) -> list[dict[str, Any]]:
    path = mbpp_dataset_path(moulinette_dir)
    if not path.is_file():
        raise FileNotFoundError(f"MBPP dataset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def discover_mbpp_tasks(moulinette_dir: Path) -> list[int]:
    return sorted(
        int(task["task_id"])
        for task in load_mbpp_dataset(moulinette_dir)
        if task.get("split") == "test"
    )


def mbpp_agent_payload(task: dict[str, Any]) -> dict[str, Any]:
    """Reproduce InteractMBPP.get_task + MBPPTaskInput.from_moulinette."""
    imports = task.get("test_imports", [])
    tests = task.get("test_list", [])
    return {
        "task_id": task["task_id"],
        "task_definition": task["task_definition"],
        "function_definition": task["function_definition"],
        "test_imports": imports[1:] if len(imports) > 1 else [],
        "test_list": tests[1:] if len(tests) > 1 else [],
    }


def _pool_expression(
    node: ast.expr,
    known: dict[str, list[str]],
) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for item in node.elts:
            if not isinstance(item, ast.Constant) or not isinstance(
                item.value, str
            ):
                raise ValueError("pool contains a non-string value")
            values.append(item.value)
        return values
    if isinstance(node, ast.Name) and node.id in known:
        return list(known[node.id])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _pool_expression(node.left, known) + _pool_expression(
            node.right, known
        )
    raise ValueError("unsupported SWE-bench pool expression")


def discover_swebench_tasks(moulinette_dir: Path) -> list[str]:
    """Read EXAM_POOL without importing the heavyweight SWE-bench package."""
    path = moulinette_dir / "moulinette/swebench/interact.py"
    if not path.is_file():
        raise FileNotFoundError(f"SWE-bench moulinette not found: {path}")

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    known: dict[str, list[str]] = {}
    for statement in tree.body:
        if (
            not isinstance(statement, ast.Assign)
            or len(statement.targets) != 1
        ):
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id not in {"SEED_POOL", "EXAM_POOL"}:
            continue
        known[target.id] = _pool_expression(statement.value, known)

    if "EXAM_POOL" not in known:
        raise ValueError(f"EXAM_POOL not found in {path}")
    return known["EXAM_POOL"]


def moulinette_executable(moulinette_dir: Path) -> Path:
    candidate = moulinette_dir / ".venv/bin/moulinette_eval"
    if candidate.is_file():
        return candidate
    installed = shutil.which("moulinette_eval")
    if installed:
        return Path(installed)
    raise FileNotFoundError(
        f"moulinette_eval not found; run `uv sync` in {moulinette_dir}"
    )


def moulinette_python(moulinette_dir: Path) -> Path:
    candidate = moulinette_dir / ".venv/bin/python"
    if candidate.is_file():
        return candidate
    return Path(sys.executable)


def metrics_errors(benchmark: str, solution: dict[str, Any]) -> list[str]:
    limits = LIMITS[benchmark]
    checks = (
        ("iterations", solution.get("iterations"), limits["iterations"]),
        (
            "input tokens",
            solution.get("total_input_tokens"),
            limits["input_tokens"],
        ),
        (
            "output tokens",
            solution.get("total_output_tokens"),
            limits["output_tokens"],
        ),
        (
            "time seconds",
            solution.get("total_time_seconds"),
            limits["time_seconds"],
        ),
    )
    errors = []
    for label, value, maximum in checks:
        if not isinstance(value, (int, float)):
            errors.append(f"{label} is missing or is not numeric")
        elif value > maximum:
            errors.append(f"{label} {value} exceeds {maximum}")
    return errors


def contract_warnings(
    benchmark: str,
    task_id: str,
    solution: dict[str, Any],
) -> list[str]:
    warnings = []
    if str(solution.get("task_id")) != task_id:
        warnings.append(
            f"task_id is {solution.get('task_id')!r}, expected {task_id!r}"
        )
    if solution.get("benchmark") != benchmark:
        warnings.append(
            "benchmark is "
            f"{solution.get('benchmark')!r}, expected {benchmark!r}"
        )

    steps = solution.get("steps")
    if isinstance(steps, list):
        if solution.get("iterations") != len(steps):
            warnings.append("iterations does not match the number of steps")
        input_total = sum(
            step.get("input_tokens", 0)
            for step in steps
            if isinstance(step, dict)
        )
        output_total = sum(
            step.get("output_tokens", 0)
            for step in steps
            if isinstance(step, dict)
        )
        if solution.get("total_input_tokens") != input_total:
            warnings.append("total_input_tokens does not match the steps")
        if solution.get("total_output_tokens") != output_total:
            warnings.append("total_output_tokens does not match the steps")
    return warnings


def exam_pass_probability(
    total: int,
    passed: int,
    draws: int,
    required: int,
) -> float:
    if not (0 <= passed <= total) or not (0 <= required <= draws <= total):
        raise ValueError("invalid probability arguments")
    denominator = math.comb(total, draws)
    favorable = 0
    for successes in range(required, draws + 1):
        failures = draws - successes
        if successes <= passed and failures <= total - passed:
            favorable += math.comb(passed, successes) * math.comb(
                total - passed, failures
            )
    return favorable / denominator


def safe_task_name(task_id: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in task_id
    )


def solution_summary(solution: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "success",
        "iterations",
        "total_requests",
        "total_input_tokens",
        "total_output_tokens",
        "total_time_seconds",
        "error",
    )
    return {field: solution.get(field) for field in fields}


class EvaluationRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.root = ROOT
        self.moulinette_dir = args.moulinette_dir.resolve()
        self.output_dir = args.output_dir.resolve()
        self.eval_cli = moulinette_executable(self.moulinette_dir)
        self.env = os.environ.copy()
        self.env["PYTHONUNBUFFERED"] = "1"
        self.results: list[dict[str, Any]] = []

    def full_pool(self, benchmark: str) -> list[str]:
        if benchmark == "mbpp":
            return [
                str(task) for task in discover_mbpp_tasks(self.moulinette_dir)
            ]
        return discover_swebench_tasks(self.moulinette_dir)

    def is_complete_pool(
        self,
        benchmark: str,
        tasks: list[str],
    ) -> bool:
        complete = self.full_pool(benchmark)
        return len(tasks) == len(complete) and set(tasks) == set(complete)

    def preflight(self, selected: dict[str, list[str]]) -> None:
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("docker executable not found")
        try:
            check = subprocess.run(
                [docker, "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("docker info timed out") from error
        if check.returncode != 0:
            raise RuntimeError("Docker daemon is not available")

        for benchmark, tasks in selected.items():
            if not tasks:
                continue
            providers_name = (
                "mbpp_providers.json"
                if benchmark == "mbpp"
                else "swe_providers.json"
            )
            providers_path = self.root / "config" / providers_name
            providers = json.loads(providers_path.read_text(encoding="utf-8"))
            if not any(
                self.env.get(provider.get("api_key", ""))
                for provider in providers
            ):
                raise RuntimeError(
                    f"no configured API key is available for {benchmark}"
                )

        if selected.get("mbpp"):
            inspect = subprocess.run(
                [docker, "image", "inspect", "python:3.11-slim"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if inspect.returncode != 0:
                print("Pulling required MBPP image python:3.11-slim...")
                pull = run_logged(
                    [docker, "pull", "python:3.11-slim"],
                    cwd=self.root,
                    env=self.env,
                    log_path=self.output_dir / "preflight/docker-pull.log",
                    timeout=600,
                )
                if pull.returncode != 0:
                    raise RuntimeError(
                        "failed to pull python:3.11-slim; see preflight log"
                    )

    def selected_tasks(self) -> dict[str, list[str]]:
        selected: dict[str, list[str]] = {}
        if self.args.benchmark in {"all", "mbpp"}:
            mbpp = (
                [str(task) for task in self.args.mbpp_task]
                if self.args.mbpp_task
                else [
                    str(task)
                    for task in discover_mbpp_tasks(self.moulinette_dir)
                ]
            )
            selected["mbpp"] = mbpp
        if self.args.benchmark in {"all", "swebench"}:
            swebench = (
                self.args.swe_task
                if self.args.swe_task
                else discover_swebench_tasks(self.moulinette_dir)
            )
            selected["swebench"] = list(swebench)

        rng = random.Random(self.args.seed)
        for benchmark, tasks in selected.items():
            if self.args.shuffle:
                rng.shuffle(tasks)
            if self.args.limit is not None:
                selected[benchmark] = tasks[: self.args.limit]
        return selected

    def prepare_mbpp_task(self, task_id: str, output: Path) -> CommandResult:
        tasks = load_mbpp_dataset(self.moulinette_dir)
        try:
            task = next(
                task for task in tasks if str(task["task_id"]) == task_id
            )
        except StopIteration as error:
            raise ValueError(f"unknown MBPP task {task_id}") from error
        write_json(output, mbpp_agent_payload(task))
        return CommandResult(0, 0.0)

    def prepare_swebench_task(
        self,
        task_id: str,
        output: Path,
        log_path: Path,
    ) -> CommandResult:
        command = [
            str(self.eval_cli),
            "dump",
            "swebench",
            "--task-id",
            task_id,
            "--output",
            str(output),
        ]
        return run_logged(
            command,
            cwd=self.root,
            env=self.env,
            log_path=log_path,
            timeout=600,
        )

    def agent_command(
        self,
        benchmark: str,
        task_file: Path,
        solution_file: Path,
    ) -> list[str]:
        if benchmark == "mbpp":
            entrypoint = self.root / "agent_mbpp.py"
            providers = self.root / "config/mbpp_providers.json"
        else:
            entrypoint = self.root / "agent_swebench.py"
            providers = self.root / "config/swe_providers.json"

        command = [
            sys.executable,
            str(entrypoint),
            "--task-file",
            str(task_file),
            "--output",
            str(solution_file),
            "--providers-file",
            str(providers),
        ]
        if self.args.provider_url:
            command.extend(
                [
                    "--provider-url",
                    self.args.provider_url,
                    "--model-name",
                    self.args.model_name,
                ]
            )
        return command

    def validate(
        self,
        benchmark: str,
        task_file: Path,
        solution_file: Path,
        log_path: Path,
    ) -> CommandResult:
        command = [
            str(self.eval_cli),
            "validate",
            benchmark,
            str(task_file),
            str(solution_file),
            "--skip-metrics=True",
        ]
        timeout = 60 if benchmark == "mbpp" else 930
        return run_logged(
            command,
            cwd=self.root,
            env=self.env,
            log_path=log_path,
            timeout=timeout,
        )

    def prior_result(self, result_file: Path) -> dict[str, Any] | None:
        if not self.args.resume or not result_file.is_file():
            return None
        try:
            result = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if self.args.retry_failed and not result.get("overall_passed", False):
            return None
        return result

    def run_task(self, benchmark: str, task_id: str) -> dict[str, Any]:
        task_dir = self.output_dir / benchmark / safe_task_name(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        result_file = task_dir / "result.json"
        previous = self.prior_result(result_file)
        if previous is not None:
            print(f"  SKIP {benchmark}:{task_id} (already completed)")
            return previous

        result_file.unlink(missing_ok=True)

        task_file = task_dir / "task.json"
        solution_file = task_dir / "solution.json"
        solution_file.unlink(missing_ok=True)
        result: dict[str, Any] = {
            "benchmark": benchmark,
            "task_id": task_id,
            "started_at": timestamp(),
            "overall_passed": False,
        }

        print(f"  RUN  {benchmark}:{task_id}")
        try:
            if benchmark == "mbpp":
                dump = self.prepare_mbpp_task(task_id, task_file)
            else:
                dump = self.prepare_swebench_task(
                    task_id,
                    task_file,
                    task_dir / "dump.log",
                )
            result["dump_exit_code"] = dump.returncode
            if dump.returncode != 0 or not task_file.is_file():
                result["status"] = "dump_failed"
                return self.finish_task(result_file, result)

            agent = run_logged(
                self.agent_command(benchmark, task_file, solution_file),
                cwd=self.root,
                env=self.env,
                log_path=task_dir / "agent.log",
                timeout=float(LIMITS[benchmark]["time_seconds"]),
            )
            result.update(
                {
                    "agent_exit_code": agent.returncode,
                    "agent_wall_time_seconds": round(agent.elapsed_seconds, 3),
                    "agent_timed_out": agent.timed_out,
                }
            )
            if not solution_file.is_file():
                result["status"] = "solution_missing"
                return self.finish_task(result_file, result)

            try:
                solution = json.loads(
                    solution_file.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError as error:
                result["status"] = "solution_invalid_json"
                result["error"] = str(error)
                return self.finish_task(result_file, result)

            result["solution"] = solution_summary(solution)
            result["metrics_errors"] = metrics_errors(benchmark, solution)
            result["contract_warnings"] = contract_warnings(
                benchmark,
                task_id,
                solution,
            )

            validation = self.validate(
                benchmark,
                task_file,
                solution_file,
                task_dir / "validation.log",
            )
            result.update(
                {
                    "validation_exit_code": validation.returncode,
                    "validation_wall_time_seconds": round(
                        validation.elapsed_seconds, 3
                    ),
                    "validation_timed_out": validation.timed_out,
                    "correctness_passed": validation.returncode == 0,
                    "metrics_passed": not result["metrics_errors"],
                }
            )
            result["overall_passed"] = (
                agent.returncode == 0
                and validation.returncode == 0
                and not result["metrics_errors"]
            )
            result["status"] = (
                "passed" if result["overall_passed"] else "failed"
            )
            return self.finish_task(result_file, result)
        except Exception as error:
            result["status"] = "runner_error"
            result["error"] = f"{type(error).__name__}: {error}"
            return self.finish_task(result_file, result)

    def finish_task(
        self,
        result_file: Path,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        result["finished_at"] = timestamp()
        write_json(result_file, result)
        label = "PASS" if result.get("overall_passed") else "FAIL"
        print(f"  {label} {result['benchmark']}:{result['task_id']}")
        return result

    def save_summary(
        self,
        selected: dict[str, list[str]],
    ) -> None:
        benchmarks: dict[str, Any] = {}
        for benchmark, tasks in selected.items():
            results = [
                result
                for result in self.results
                if result.get("benchmark") == benchmark
            ]
            passed = sum(
                bool(result.get("overall_passed")) for result in results
            )
            data: dict[str, Any] = {
                "selected": len(tasks),
                "completed": len(results),
                "passed": passed,
                "failed": len(results) - passed,
            }
            if (
                len(results) == len(tasks)
                and tasks
                and self.is_complete_pool(benchmark, tasks)
            ):
                selection = EXAM_SELECTION[benchmark]
                data["exam_pass_probability"] = exam_pass_probability(
                    len(tasks),
                    passed,
                    selection["draws"],
                    selection["required"],
                )
            benchmarks[benchmark] = data

        summary = {
            "updated_at": timestamp(),
            "output_dir": str(self.output_dir),
            "benchmarks": benchmarks,
            "results": self.results,
        }
        write_json(self.output_dir / "summary.json", summary)
        self.write_markdown_summary(summary)

    def write_markdown_summary(self, summary: dict[str, Any]) -> None:
        lines = [
            "# Complete evaluation summary",
            "",
            f"Updated: {summary['updated_at']}",
            "",
            "| Benchmark | Completed | Passed | Failed | Exam probability |",
            "|---|---:|---:|---:|---:|",
        ]
        for benchmark, data in summary["benchmarks"].items():
            probability = data.get("exam_pass_probability")
            probability_text = (
                f"{probability:.2%}" if probability is not None else "n/a"
            )
            lines.append(
                f"| {benchmark} | {data['completed']}/{data['selected']} "
                f"| {data['passed']} | {data['failed']} "
                f"| {probability_text} |"
            )

        lines.extend(
            [
                "",
                "| Task | Status | Iterations | Input | Output | Time |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for result in summary["results"]:
            solution = result.get("solution", {})
            lines.append(
                f"| {result.get('benchmark')}:{result.get('task_id')} "
                f"| {result.get('status')} "
                f"| {solution.get('iterations', '-')} "
                f"| {solution.get('total_input_tokens', '-')} "
                f"| {solution.get('total_output_tokens', '-')} "
                f"| {solution.get('total_time_seconds', '-')} |"
            )
        (self.output_dir / "summary.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    def run(self) -> int:
        selected = self.selected_tasks()
        total = sum(len(tasks) for tasks in selected.values())
        print(f"Output: {self.output_dir}")
        for benchmark, tasks in selected.items():
            print(f"{benchmark}: {len(tasks)} task(s)")
        print(f"Total: {total} task(s), sequential execution")
        timeout_seconds = sum(
            len(tasks) * LIMITS[benchmark]["time_seconds"]
            for benchmark, tasks in selected.items()
        )
        max_input_tokens = sum(
            len(tasks) * LIMITS[benchmark]["input_tokens"]
            for benchmark, tasks in selected.items()
        )
        print(
            "Theoretical maxima: "
            f"{timeout_seconds / 3600:.1f} agent-hours, "
            f"{int(max_input_tokens):,} input tokens"
        )

        write_json(self.output_dir / "manifest.json", selected)
        if self.args.dry_run:
            return 0

        self.preflight(selected)

        for benchmark, tasks in selected.items():
            for task_id in tasks:
                result = self.run_task(benchmark, task_id)
                self.results.append(result)
                self.save_summary(selected)
                if self.args.fail_fast and not result.get("overall_passed"):
                    return 1
        return (
            0
            if all(result.get("overall_passed") for result in self.results)
            else 1
        )


def default_output_dir() -> Path:
    label = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_RESULTS_ROOT / label


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run every MBPP test-split task and every SWE-bench exam-pool "
            "task, then validate correctness and metric limits."
        )
    )
    parser.add_argument(
        "--benchmark",
        choices=("all", "mbpp", "swebench"),
        default="all",
    )
    parser.add_argument(
        "--moulinette-dir",
        type=Path,
        default=DEFAULT_MOULINETTE,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir(),
    )
    parser.add_argument("--provider-url")
    parser.add_argument("--model-name")
    parser.add_argument("--mbpp-task", type=int, action="append", default=[])
    parser.add_argument("--swe-task", action="append", default=[])
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N selected tasks per benchmark.",
    )
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if bool(args.provider_url) != bool(args.model_name):
        parser.error(
            "--provider-url and --model-name must be provided together"
        )
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(ROOT / "src/agent/.env", override=False)
    try:
        return EvaluationRunner(args).run()
    except KeyboardInterrupt:
        print("\nInterrupted; completed task results remain resumable.")
        return 130
    except Exception as error:
        print(
            f"runner error: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
