
from typing import Any
from openai import OpenAI
import os
import sys
import json
from dotenv import load_dotenv
import re


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
        except Exception as e:
            raise LlmApiError(
                f"can't load providers in: {providers_file} error: {e}")
        for url in self.urls:
            url["client"] = OpenAI(
                base_url=url["url"],
                api_key=os.getenv(url["api_key"], "0")
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
                        api_key=os.getenv("EXTRA_API_KEY", "0")
                    )
                })
        if self.iurl == -1:
            self.iurl = len(self.urls) - 1
            self.imodel = len(self.urls[self.iurl]["models"]) - 1

    def response(self, msg: list[dict[str, str | int]]) -> dict[str, str | int]:

        retries = 0
        while 1:
            try:
                params = {
                    "model": self.urls[self.iurl]["models"][self.imodel],
                    "messages": msg
                }

                self.requests += 1
                response = self.urls[self.iurl]["client"].chat.completions.create(
                    **params)
                return {
                    "llm_input": msg[-1]["content"],
                    "llm_output": response.choices[0].message.content,
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
                Log.add_logs(msg)
                print("response error; ", msg, file=sys.stderr)
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
            "messages": cls.messages,
            "memory_mode": cls.memory_mode,
            "max": cls.max,
            "true_max": cls.true_max,
            "save_len": cls.save_len,
            "current_objective": cls.current_objective,
            "main_hints": cls.main_hints,
            "current_hints": cls.current_hints
        }
        cls._new_data = data

    @classmethod
    def init(cls, base_prompt_system: str, base_prompt_user: str, launch_objective: str = "") -> None:
        cls.memory_mode = False

        cls.messages = [{"role": "system", "content": base_prompt_system}]
        cls.messages.append({"role": "user", "content": base_prompt_user})

        if launch_objective:
            cls.memory_mode = True
            cls.max = 0
            cls.true_max = 0
            cls.save_len = 2

            cls.current_objective = ""
            cls.main_hints: list[str] = []
            cls.current_hints: list[list[str]] = []

            current_objective = f"<CURRENT_OBJECTIVE>\n{launch_objective}\n</CURRENT_OBJECTIVE>"
            cls.current_hints.append(
                [current_objective]
            )
            cls.add_message(current_objective)

    # Spceial Method usable by the llm
    @classmethod
    def add_main_objective_hint(cls, msg: str) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        msg = f"\n<MAIN_OBJECTIVE_HINT>\n{msg}\n</MAIN_OBJECTIVE_HINT>"
        cls.main_hints.append(msg)
        cls.add_message(msg)

        print("main ojective hint saved")
        cls.save_data()

    # Spceial Method usable by the llm
    @classmethod
    def add_current_objective_hint(cls, msg: str) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        msg = f"\n<CURRENT_OBJECTIVE_HINT>\n{msg}\n</CURRENT_OBJECTIVE_HINT>"
        cls.current_hints[-1].append(msg)
        cls.add_message(msg)

        print("current ojective hint saved")
        cls.save_data()

    # Spceial Method usable by the llm
    @classmethod
    def set_new_current_objective(cls, objective: str, previous_current_objective_status: str) -> None:
        if objective == cls.current_objective:
            return
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        c_obj = previous_current_objective_status 
        if cls.current_objective:
            main_hint = f"OBJECTIVE:{cls.current_objective}. STATUS:{c_obj}"
            cls.add_main_objective_hint(main_hint)
        cls.current_objective = objective
        new_objective = f"<CURRENT_OBJECTIVE>\n{objective}\n</CURRENT_OBJECTIVE>"
        cls.current_hints.append([new_objective])
        cls.add_message(new_objective)
        
        print("new current ojective saved")
        cls.save_data()

    # if len(all_memory) > cls.max + len(important_memory) ...
    # if len(all_memory) > cls.true_max ...
    @classmethod
    def compress_memory(cls) -> None:
        # TODO
        pass

    @classmethod
    def get_messages(cls) -> list[dict[str, str]]:
        return cls.messages

    @classmethod
    def add_message(cls, msg: str, role: str = "user") -> None:
        if cls.messages[-1]["role"] != role:
            cls.messages.append({"role": role, "content": msg})
        else:
            cls.messages[-1]["content"] += f"\n{msg}"

    @classmethod
    def get_message_codes(cls, model: str) -> list[str]:
        # TODO

        out = []
        message = cls.messages[-1]
        if message["role"] != "assistant":
            raise MemoryPromptError(
                "last message not from assistant, can't extract code")
        data = message["content"]
        match model:
            case "test":
                pass
            case "test2":
                pass
            case _:
                try:
                    out = re.findall(r"```python\s*\n(.*?)```",
                                     data, flags=re.DOTALL)
                except Exception:
                    pass
        return out
