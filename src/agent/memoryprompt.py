
from typing import Any
from pydantic import BaseModel
import re

from src.swebench.testbed import DockerTestbed
from src.agent.helpers import Log


class MemoryPromptError(Exception):
    pass


class MemoryPromptSave(Exception):

    def __str__(self):
        return str(self.data)
    
    def __init__(self, data):
        self.data = data


class MemoryPrompt:

    _new_data: dict[str, Any] = dict()

    @classmethod
    def _get_new_prompt_data(cls) -> dict[str, Any]:
        return cls._new_data

    @classmethod
    def load_data(cls, data: dict[str, Any]) -> None:
        for key, elem in data.items():
            setattr(cls, key, elem)
        cls._new_data = dict()

    @classmethod
    def save_data(cls) -> None:
        data = {
            "memory_mode": cls.memory_mode,
            "go_next": cls.go_next,
            "base_user": cls.base_user,
            "messages": cls.messages,
            "hints": cls.hints,
            "hypothesis": cls.hypothesis,
            "next_step": cls.next_step,
            "step_memory": cls.step_memory,
            "current_step": cls.current_step,
            "previous_step": cls.previous_step,
            "loop_retry": cls.loop_retry
        }
        cls._new_data = data

    @classmethod
    def warn_message(cls, info: str) -> str:
        out = (
            f"<DIRECTIVE>\n'{info}' has already been executed. You are certainly engaging an infinite llm loop.\n"
            "Be attentive of KNOWN_INFO, and make a new assumtion to verify at next execution\n"
            "exemple 1: ```pyhton\nadd_current_objective_hint('we have now enough information and need to resolve the problem')\n```\n"
            "exemple 2: ```pyhton\nadd_current_objective_hint('i think the file x have already been modified,"
            " we need to git restore and edit it with a proper complete python code block')\n```\n"
            "\n</DIRECTIVE>"
        )
        return out

    @classmethod
    def init(cls, base_prompt_system: str, base_prompt_user: str, memory_mode: bool = False) -> None:
        cls.memory_mode = False
        cls.go_next = False

        cls.messages = [{"role": "system", "content": base_prompt_system}]
        cls.messages.append({"role": "user", "content": base_prompt_user})

        cls.base_user = base_prompt_user

        if memory_mode:
            cls.memory_mode = True
            cls.hints: list[str] = []
            cls.hypothesis: list[dict[str, str]] = []
            cls.add_message("\n<KNOWN_INFO> no saved data </KNOWN_INFO>\n")
            cls.step_memory = []
            cls.next_step = {
                            "investigate": "hypothesis", "hypothesis": "modifie",
                            "modifie": "test", "test": "rule_on",
                            "rule_on": "clean memory",
                            "clean memory": "reset",
                            "reset": "investigate",
            }
            cls.current_step = "investigate"
            cls.previous_step = "investigate"
            cls.loop_retry = 0
        else:
            cls.tries = []

    # Spceial Method usable by the llm
    @classmethod
    def save_missing_info(cls, msg: str) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        if msg in cls.hints:
            print("hint already knowed")
            return

        cls.hints.append(msg)
        print("hint saved")
        cls.save_data()

    @classmethod
    def simple_save_missing_info(cls, msg: str) -> None:

        if msg in cls.hints:
            print("hint already knowed")
            return

        cls.hints.append(msg)
        print("hint saved")
        cls.simple_go_next_step()

    @classmethod
    def save_try(cls, msg: str) -> None:
        if msg not in cls.tries:
            cls.tries.append(msg)

    # Spceial Method usable by the llm
    @classmethod
    def go_next_step(cls) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")
        if cls.current_step in ["investigate", "test"]:
            raise ValueError("Impossible to use go_next_step in the current phase")

        print(f"step set to {cls.next_step[cls.current_step]}")
        cls.go_next = True
        cls.step_memory = []
        cls.loop_retry = 0
        cls.save_data()

    @classmethod
    def simple_go_next_step(cls) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        print(f"step set to {cls.next_step[cls.current_step]}")
        cls.go_next = True
        cls.step_memory = []
        cls.loop_retry = 0

    class CheckHypArgs(BaseModel):
        files: list[str]
        msg: str

    @classmethod
    def loop_reaction_msg(cls, failer: str) -> str:
        if cls.loop_retry == 1:
            out = (
                f"['{failer}' rejected cos duplicate information]\n"
                f"You repeated ! check KNOWN_INFO and propose something not in it !\n"
                "Your next proposal must differ from already explored hypotheses !\n"
            )
        else:
            out = (
                f"['{failer}' rejected cos duplicate information. (#[{cls.loop_retry})]\n"
                f"FORBIDDEN TO COPY AND USE DATA OF KNOWN_INFO !\n"
                f"Find unexplored data. Then call {failer} with one of theses !\n"
                f"Call {failer} with arguments differ from KNOWN_INFO hypotheses !"
            )
        if cls.loop_retry <= 2:
            return out

        anti_repetition_words = [
            "new", "novel", "fresh", "original", "innovative", "inventive",
            "unprecedented", "unseen", "untried", "unexplored", "uncharted",
            "first-of-its-kind", "groundbreaking", "pioneering", "cutting-edge",
            "state-of-the-art",

            "different", "distinct", "distinctive", "unique", "singular",
            "one-of-a-kind", "unlike", "alternative", "divergent", "unconventional",
            "unorthodox", "atypical", "non-obvious", "unexpected", "surprising",
            "unfamiliar",

            "varied", "diverse", "versatile", "multifaceted", "assorted", "mixed",
            "eclectic", "wide-ranging", "many-sided", "alternating", "rotating",

            "changing", "evolving", "shifting", "progressive", "incremental",
            "adaptive", "dynamic", "transformative", "pivotal", "decisive",
            "game-changing",

            "creative", "imaginative", "resourceful", "ingenious", "clever", "smart",
            "lateral", "out-of-the-box", "experimental", "exploratory",

            "informative", "insightful", "revealing", "enlightening", "illuminating",
            "meaningful", "substantive", "additive", "productive", "fruitful", "useful",
        ]
        magic1 = random.choice(anti_repetition_words)
        while 1:
            magic2 = random.choice(anti_repetition_words) 
            if magic1 != magic2:
                break
        out += f"\nBe {magic1} and {magic2} in your response."
        return out

    # Spceial Method usable by the llm
    @classmethod
    def propose_hypothesis(cls, files: list[str], msg: str) -> None:
        try:
            cls.CheckHypArgs(files=files, msg=msg)
        except Exception:
            raise ValueError("files argument need to be a list of strings, and msg a string")
        if cls.current_step not in ["investigate", "hypothesis"]:
            print("You need to be asked to use this function")
            return

        hyp = f"{msg} | [{', '.join(files)}]"

        for elem in cls.hypothesis:
            if elem["hyp"] == hyp:
                cls.loop_retry += 1
                print(
                    cls.loop_reaction_msg("propose_hypothesis")
                )
                if cls.current_step == "investigate":
                    cls.simple_go_next_step()
                cls.save_data()
                return

        print("new hypothesis engaged")
        cls.hypothesis.append({"hyp": hyp, "rule_on": "pending"})
        cls.current_step = "hypothesis"
        cls.simple_go_next_step()
        cls.save_data()

    # Spceial Method usable by the llm
    @classmethod
    def rule_on_hypothesis(cls, verdict: str, evidence: str) -> None:
        if cls.current_step not in ["test", "rule_on"]:
            print("You need to be asked to use this function")
            return

        rule_on = f"verdict: {verdict} | evidence: {evidence}"

        for elem in cls.hypothesis:
            if elem.get("rule_on") == rule_on:
                cls.loop_retry += 1
                print(
                    cls.loop_reaction_msg("rule_on_hypothesis")
                )
                if cls.current_step == "test":
                    cls.simple_go_next_step()
                cls.save_data()
                return

        print("rule_on_hypothesis saved")
        cls.hypothesis[-1]["rule_on"] = rule_on
        cls.current_step = "rule_on"
        cls.simple_go_next_step()
        cls.save_data()

    @classmethod
    def check_step_loop(cls) -> bool:
        if len(cls.step_memory) < 2:
            return False

        for i, elem in enumerate(cls.step_memory):
            for memory in cls.step_memory[i + 1:]:
                if elem == memory:
                    cls.messages.pop(-1)
                    if not "<INSTRUCTIONS>" in cls.messages[-1]["content"]:
                        raise ValueError("no instructions during check_step_loop")
                    cls.messages[-1]["content"] = cls.messages[-1]["content"].split("<INSTRUCTIONS>")[0].strip()
                    if not cls.messages[-1]["content"].strip():
                        raise ValueError("impossible cut during check_step_loop")
                    if cls.current_step not in ["hypothesis", "rule_on"]:
                        cls.simple_go_next_step()
                    Log.print("duplicate deleted")
                    return True
        return False

    @classmethod
    def apply_go_next_step(cls, testbed: DockerTestbed) -> None:

        if not cls.go_next:
            return
        cls.go_next = False

        cls.current_step = cls.next_step[cls.current_step]
        if cls.current_step == "reset":
            cls.compress_memory()
            cls.current_step = cls.next_step[cls.current_step]
            testbed.reset_data()
   
    @classmethod
    def new_base_user_prompt(cls) -> str:
        
        msg = cls.base_user
        
        if cls.memory_mode:
            if not cls.hints and not cls.hypothesis:
                return msg

            msg += "\n<KNOWN_INFO>\n"
            for i, elem in enumerate(cls.hints, 1):
                msg += f"[{i}] {elem}\n"
            if cls.hypothesis:
                msg += "<HYPOTHESES>\n"
                for elem in cls.hypothesis:
                    msg += f"{elem['hyp']} | {elem['rule_on']}"
                msg += "</HYPOTHESES>\n"

            msg += "</KNOWN_INFO>"
        elif len(cls.tries) > 1:
            msg += "\n<FAILED_ATTEMPTS>\n"
            for i, elem in enumerate(cls.tries[:-1], 1):
                msg += f"<TRY_[{i}]>\n{elem}\n</TRY_[{i}]>\n"
            msg += "</FAILED_ATTEMPTS>"
        return msg

    @classmethod
    def compress_memory(cls) -> None:

        cls.messages = cls.messages[:2]
        msg = cls.new_base_user_prompt()
        cls.messages[1]["content"] = msg

    @classmethod
    def compress_user_msg(cls, previous_sandbox_output: str, executed: bool) -> None:

        if len(cls.messages) == 3:
            cls.messages[-2]["content"] = cls.new_base_user_prompt()
        else:
            if executed:
                info = previous_sandbox_output
                if not info.replace("''", "", 1).strip():
                    info = "'[Code executed, but no print occured]'"
                if cls.memory_mode:
                    flag = f"{cls.previous_step.upper()}_OUTPUT"
                else:
                    flag = "OUTPUT"
                msg = (
                    f"<{flag}>"
                    f"\n{info}\n"
                    f"</{flag}>"
                )
            else:
                msg = "[The previous message did not execute any code.]"

            cls.messages[-2]["content"] = msg
        if cls.memory_mode:
            cls.previous_step = cls.current_step

    @classmethod
    def get_messages(cls) -> list[dict[str, str]]:
        return cls.messages

    @classmethod
    def add_message(cls, msg: str, role: str = "user") -> None:
        if cls.messages[-1]["role"] != role:
            cls.messages.append({"role": role, "content": msg})
        else:
            cls.messages[-1]["content"] += f"\n{msg}"
        if cls.memory_mode and role == "assistant":
            cls.step_memory.append(msg.strip())

    @classmethod
    def get_message_codes(cls) -> list[str]:

        message = cls.messages[-1]
        if message["role"] != "assistant":
            raise MemoryPromptError(
                "last message not from assistant, can't extract code")
        data = message["content"]
        out = re.findall(r"```python\s*\n(.*?)```",
                         data, flags=re.DOTALL)
        return out
