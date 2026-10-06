import time
from typing import NamedTuple

from src.common.models import StepMetrics


class Limits(NamedTuple):
    iterations: int
    input_tokens: int
    output_tokens: int
    seconds: float


class Budget:
    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.deadline = time.monotonic() + limits.seconds - 30.0

    def stop_reason(self, steps: list[StepMetrics]) -> str | None:
        if len(steps) >= self.limits.iterations:
            return f"iteration limit reached ({self.limits.iterations})"
        if time.monotonic() >= self.deadline:
            return f"time budget reached ({self.limits.seconds}s)"

        used = sum(step.input_tokens for step in steps)
        worst = max((step.input_tokens for step in steps), default=0)
        if used + worst > self.limits.input_tokens:
            return (f"input token budget reached ({used} used of "
                    f"{self.limits.input_tokens}, no room for another step)")

        used = sum(step.output_tokens for step in steps)
        worst = max((step.output_tokens for step in steps), default=0)
        if used + worst > self.limits.output_tokens:
            return (f"output token budget reached ({used} used of "
                    f"{self.limits.output_tokens}, no room for another step)")

        return None
