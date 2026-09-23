from typing import Any
import sys


class FinalAnswer(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


def final_answer(value: Any) -> None:
    print(f"<FinalAnswerExit>{value}", file=sys.stderr)
    sys.exit(42)
