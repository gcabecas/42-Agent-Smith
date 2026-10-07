
from typing import Any
from openai import OpenAI, BadRequestError
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


    def response(self, msg: list[dict[str, str | int]], mode: str) -> dict[str, str | int]:

        retries = 0
        if mode == "code":
            temperature = 0.3
        else:
            temperature = 0.7

        Log.print("[sending llm demand ..]")
        while 1:
            try:
                params = {
                    "model": self.urls[self.iurl]["models"][self.imodel],
                    "messages": msg,
                    "temperature": temperature
                }
                self.requests += 1
                try:
                    response = self.urls[self.iurl]["client"].chat.completions.create(
                        **params)
                except BadRequestError:
                    Log.print(f"'temperature' not handled by: {self.get_current()}")
                    params.pop("temperature")
                    response = self.urls[self.iurl]["client"].chat.completions.create(
                        **params)
                    self.requests += 1

                Log.print("[llm response recieved.]")
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
    _msg_buffer: str = ""

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
            "base_user": cls.base_user,
            "messages": cls.messages,
            "main_hints": cls.main_hints,
            "current_hints": cls.current_hints,
            "_msg_buffer": cls._msg_buffer
        }
        cls._new_data = data

    @classmethod
    def warn_message(cls, info: str) -> str:
        out = (
            f"<DANGEROUS_ERROR>\nThis '{info}' it's already knowed and/or tracked. You are certainly engaging an infinite llm loop.\n"
            "Check KNOWN_DATA ! and check directive !\n"
            "DO SOMETHING PROGRESSING THE RESOLVING !\n</DANGEROUS_ERROR>"
        )
        return out

    @classmethod
    def init(cls, base_prompt_system: str, base_prompt_user: str, launch_objective: str = "") -> None:
        cls.memory_mode = False

        cls.messages = [{"role": "system", "content": base_prompt_system}]
        cls.messages.append({"role": "user", "content": base_prompt_user})

        if launch_objective:
            cls.memory_mode = True
            cls.base_user = base_prompt_user

            cls.main_hints: list[str] = []
            cls.current_hints: list[list[str]] = []

            current_objective = f"<current_objective>\n{launch_objective}\n</current_objective>\n"
            cls.current_hints.append(
                [current_objective]
            )
            cls.add_message(current_objective)

    @classmethod
    def apply_buffer(cls) -> None:
        cls.add_message(cls._msg_buffer)
        cls._msg_buffer = ""

    # Spceial Method usable by the llm
    @classmethod
    def add_main_objective_hint(cls, msg: str) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        if msg in cls.main_hints[1:]:
            print(cls.warn_message("main ojective hint"))
            return

        hint = f"<main_objective_hint>\n{msg}\n</main_objective_hint>\n"
        cls.main_hints.append(msg)
        cls._msg_buffer += hint

        print("main ojective hint saved")
        cls.save_data()

    # Spceial Method usable by the llm
    @classmethod
    def add_current_objective_hint(cls, msg: str) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        if msg in cls.current_hints[-1][1:]:
            print(cls.warn_message("current ojective hint"))
            return

        cls.current_hints[-1].append(msg)
        hint = f"<current_objective_hint>\n{msg}\n</current_objective_hint>\n"
        cls._msg_buffer += hint

        print("current ojective hint saved")
        cls.save_data()

    # Spceial Method usable by the llm
    @classmethod
    def set_new_current_objective(cls, objective: str) -> None:
        if objective == cls.current_hints[-1][0]:
            print(cls.warn_message("objective"))
            return
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        new_objective = f"<current_objective>\n{objective}\n</current_objective>\n"
        cls.current_hints.append([objective])
        cls._msg_buffer += new_objective
        
        print("new current ojective saved")
        cls.save_data()

    # Spceial Method usable by the llm
    @classmethod
    def delete_hint(cls, source_objective: str, hint_id: int) -> None:

        for elem in cls.current_hints[1:]:
            if source_objective == elem[0]:
                if len(elem) > hint_id > 0:
                    elem.pop(hint_id)
                    print("hint deleted successfufly")
                    cls.save_data()
                    return
                break
        if "main" in source_objective:
            hint_id -= 1
            if len(cls.main_hints) > hint_id >= 0:
                cls.main_hints.pop(hint_id)
                print("hint deleted successfully")
                cls.save_data()
                return
        print(f"[{hint_id}] not found in {source_objective}")
        

    @classmethod
    def compress_memory(cls) -> None:

        firsts_saved = 2
        threshold = 5
        lasts_saved = 4

        if len(cls.messages) - firsts_saved >= threshold:

            msg = cls.base_user
            if len(cls.current_hints) >= 2 or cls.main_hints:
                msg += "<KNOWN_DATA>\n"
                if cls.main_hints:
                    for j, elem in enumerate(cls.main_hints, 1):
                        msg += f"<hint_id:{j}>{elem}<hint_id:{j}>\n"

                    msg += (
                            "<main_objective_hints>\n" +
                            "\n".join(cls.main_hints) +
                            "\n</main_objective_hints>\n"
                    )
                if len(cls.current_hints) > 2:
                    msg += "<previous_objectives>\n"
                    for elem in cls.current_hints[1:-1]:
                        if len(elem[1:]) > 1:
                            for j, hint in enumerate(elem[1:], 1):
                                msg += f"<{elem[0]}>: <hint_id:{j}>{hint}</hint_id:{j}>\n"
                        else:
                            msg += f"<{elem[0]}>\n"

                    msg += "</previous_objectives>\n"
                msg += (
                        f"<current_objective>\n{cls.current_hints[-1][0]}\n</current_objective>\n"
                )
                if len(cls.current_hints[-1]) > 1:
                    msg += f"<current_objective_hints>\n"
                    for j, elem in enumerate(cls.current_hints[-1][1:], 1):
                        msg += f"[{j}]: {elem}\n"
                    msg += f"</current_objective_hints>\n"
                msg += "</KNOWN_DATA>\n"

            if cls.messages[-1]["role"] != "user":
                raise ValueError("impossible last role, can´t compress memory")
            if len(cls.messages) <= firsts_saved + lasts_saved:
                raise ValueError("impossible save data")
        
            cutted = cls.messages[-lasts_saved:]
            cls.messages = cls.messages[:firsts_saved]
            cls.messages[1]["content"] = msg
            cls.messages += cutted
        

    def hard_compress_memory(cls) -> None:
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
    def get_message_codes(cls) -> list[str]:

        message = cls.messages[-1]
        if message["role"] != "assistant":
            raise MemoryPromptError(
                "last message not from assistant, can't extract code")
        data = message["content"]
        out = re.findall(r"```python\s*\n(.*?)```",
                         data, flags=re.DOTALL)
        return out
