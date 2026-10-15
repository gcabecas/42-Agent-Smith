
from typing import Any
from pydantic import BaseModel, ConfigDict
from openai import OpenAI, BadRequestError
import os
import sys
import json
from dotenv import load_dotenv
import re
import random

from src.agent.stepmetrics import StepMetrics
from src.swebench.testbed import DockerTestbed


def set_file_name(path: str, extension: str) -> str:
    """ choose the file name dependig of existing files """
    from pathlib import Path
    from os.path import exists

    Path(Path(path).parent).mkdir(parents=True, exist_ok=True)
    while 1:
        if exists(path):
            s_case = path.removesuffix(extension).split('_')
            sn_case = s_case[-1]
            if sn_case.isdigit():
                s = f"{'_'.join(s_case[:-1])}_{int(sn_case) + 1}" + extension
                path = s
            else:
                path = path.removesuffix(extension) + "_1" + extension
        else:
            break
    return path


class Log:
    save_path = set_file_name("logs/log.txt", ".txt")

    @classmethod
    def print(cls, *args) -> None:
        try:
            with open(cls.save_path, "a") as f_open:
                for elem in args:
                    print(elem, file=sys.stderr)
                    f_open.write(str(elem) + "\n")
        except Exception as e:
            print(f"Logging Error ! : {e}", file=sys.stderr)


class Provider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    models: list[str]
    url: str
    api_key: str


class ProvidersList(BaseModel):
    data: list[Provider]


class LlmApiError(Exception):
    pass


class LlmApi:

    def __str__(self) -> str:
        info = "\n".join([str(u) for u in self.urls])
        return f"{self.iurl}:iurl {self.imodel}:imodel\n{info}\n"

    def __init__(self, providers_file: str, baseurl: str = "", basemodel: str = "") -> None:
        self.iurl = -1
        self.imodel = -1
        self.requests = 0
        load_dotenv()
        try:
            with open(providers_file, "r") as f_open:
                self.urls = json.load(f_open)
                ProvidersList(data=self.urls)
        except Exception as e:
            raise LlmApiError(
                f"can't load providers in: {providers_file} error: {e}")
        for url in self.urls:
            url["client"] = OpenAI(
                base_url=url["url"],
                api_key=os.getenv(url["api_key"], "0"),
                timeout=60.0
            )

        if baseurl and not basemodel:
            raise LlmApiError("url set need a model")
        if not baseurl and basemodel:
            raise LlmApiError("model set need an url")
        if baseurl and basemodel:
            if not baseurl.endswith("/"):
                baseurl = f"{baseurl}/"
            i = 0
            for url in self.urls:
                if url["client"].base_url == baseurl:
                    if basemodel not in url["models"]:
                        url["models"].append(basemodel)
                        self.iurl = i
                        self.imodel = len(url["models"]) - 1
                        break
                    else:
                        self.iurl = i
                        self.imodel = url["models"].index(basemodel)
                        break
                i += 1
            if i == len(self.urls):
                self.urls.append({
                    "name": baseurl, "models": [basemodel],
                    "client": OpenAI(
                        base_url=baseurl,
                        api_key=os.getenv("EXTRA_API_KEY", "0"),
                        timeout=60.0
                    )
                })
        if self.iurl == -1:
            self.iurl = len(self.urls) - 1
            self.imodel = len(self.urls[self.iurl]["models"]) - 1


    def response(self, messages: list[dict[str, str | int]], temperature: float = 0.1) -> dict[str, str | int]:

        retries = 0

        while 1:
            try:
                params = {
                    "model": self.urls[self.iurl]["models"][self.imodel],
                    "messages": messages,
                    "temperature": temperature
                }
                self.requests += 1
                try:
                    Log.print(f"[sending llm '{self.get_current()}' demand ...]")
                    response = self.urls[self.iurl]["client"].chat.completions.create(
                        **params)
                    output = response.choices[0].message.content
                    Log.print(f"[llm response recieved.]\n{output}\n[/llm response recieved.]")
                except BadRequestError:
                    Log.print(f"'temperature' not handled by: {self.get_current()}")
                    params.pop("temperature")
                    response = self.urls[self.iurl]["client"].chat.completions.create(
                        **params)
                    self.requests += 1

                if not isinstance(output, str) or output == "":
                    raise LlmApiError("llm output is empty")
                return {
                    "llm_input": messages[-1]["content"],
                    "llm_output": output,
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "api_url": self.urls[self.iurl]["url"],
                    "model_name": self.get_current(),
                    "retries": retries
                }
            except Exception as e:
                retries += 1
                usr = self.urls[self.iurl]
                msg = (
                    f"{usr['name']}"
                    f"|{usr['models'][self.imodel]}: {e}"
                )
                Log.print("response error; ", msg)
                self.next()
                # time.sleep(0.1)
        return dict()

    def next(self) -> None:
        if self.imodel == 0:
            if self.iurl == 0:
                self.iurl = len(self.urls) - 1
            else:
                self.iurl -= 1
            self.imodel = len(self.urls[self.iurl]["models"]) - 1
        else:
            self.imodel -= 1

    def get_current(self) -> str:
        return self.urls[self.iurl]["models"][self.imodel]


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

        if memory_mode:
            cls.memory_mode = True
            cls.base_user = base_prompt_user
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
            cls.hints: list[str] = []
            cls.hypothesis: list[dict[str, str]] = []
            cls.loop_retry = 0

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
        cls.go_next_step()
        cls.save_data()

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
        known_info = cls.new_base_user_prompt(False)
        if cls.loop_retry == 1:
            out = (
                f"[{failer.upper()} REJECTED - DUPLICATE]\n"
                f"You repeated !"
                f"Already explored, check KNOWN_INFO !\n"
                "Your next proposal must differ in file, function, or root cause.\n"
                f"Call {failer} now."
            )
        else:
            out = (
                f"[{failer.upper()} REJECTED - DUPLICATE #[{cls.loop_retry}]\n"
                f"FORBIDDEN TO COPY AND USE DATA OF KNOWN_INFO !\n"
                f"Find unexplored candidates. Then call propose_hypothesis with one of theses !\n"
                f"Call {failer} with arguments differ from KNOWN_DATA hypotheses."
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
    def check_step_loop(cls) -> None:
        if len(cls.step_memory) < 2:
            return
        
        for i, elem in enumerate(cls.step_memory[:-1], 1):
            for memory in cls.step_memory[i:]:
                if elem == memory:
                    cls.messages.pop(-1)
                    if cls.current_step not in ["hypothesis", "rule_on"]:
                        cls.simple_go_next_step()
                    Log.print("duplicate deleted")
                    return

    @classmethod
    def apply_go_next_step(cls, testbed: DockerTestbed) -> None:
        cls.check_step_loop()

        if not cls.go_next:
            return
        cls.go_next = False

        cls.current_step = cls.next_step[cls.current_step]
        if cls.current_step == "reset":
            cls.compress_memory()
            cls.current_step = cls.next_step[cls.current_step]
            testbed.reset_data()
   
    @classmethod
    def new_base_user_prompt(cls, with_base: bool = True) -> str:
        
        if with_base:
            msg = cls.base_user
        else:
            msg = ""
        
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

        msg += "</KNOWN_INFO\n>"
        return msg

    @classmethod
    def compress_memory(cls) -> None:

        cls.messages = cls.messages[:2]
        msg = cls.new_base_user_prompt()
        cls.messages[1]["content"] = msg

    @classmethod
    def compress_user_msg(cls, steps: list[StepMetrics]) -> None:

        if len(cls.messages) == 3:
            cls.messages[-2]["content"] = cls.new_base_user_prompt()
        else:
            info = steps[-2].sandbox_output
            if not info.replace("''", "", 1).strip():
                info = "'[Code executed, but no print occured]'"
            cls.messages[-2]["content"] = (
                    f"<{cls.previous_step.upper()}_OUTPUT>"
                    f"\n{info}\n"
                    f"</{cls.previous_step.upper()}_OUTPUT>"
            )
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
