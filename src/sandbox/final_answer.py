from typing import Any


class FinalAnswer(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


def final_answer(value: Any) -> None:
    raise FinalAnswer(value)
