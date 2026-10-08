
from typing import Any
from pydantic import BaseModel, ConfigDict
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


    def response(self, messages: list[dict[str, str | int]], temperature: int = 0.1) -> dict[str, str | int]:

        retries = 0

        Log.print("[sending llm demand ..]")
        while 1:
            try:
                params = {
                    "model": self.urls[self.iurl]["models"][self.imodel],
                    "messages": messages,
                    "temperature": temperature
                }
                self.requests += 1
                try:
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
            "go_next": cls.go_next,
            "base_user": cls.base_user,
            "messages": cls.messages,
            "hints": cls.hints,
            "next_step": cls.next_step,
            "current_step": cls.current_step,
            "_msg_buffer": cls._msg_buffer
        }
        cls._new_data = data

    @classmethod
    def warn_message(cls, info: str) -> str:
        out = (
            f"<DIRECTIVE>\n'{info}' has already been executed. You are certainly engaging an infinite llm loop.\n"
            "Be attentive of KNOWN_INFO, and make a new assumtion to verify at next execution\n"
            "exemple 1: ```pyhton\nadd_current_objective_hint('we have now enough informations and need to resolve the problem')\n```\n"
            "exemple 2: ```pyhton\nadd_current_objective_hint('i think the file x have already been modified,"
            " we need to git restore and edit it with a proper complete python code block')\n```\n"
            "\n</DIRECTIVE>"
        )
        return out

    @classmethod
    def init(cls, base_prompt_system: str, base_prompt_user: str, launch_objective: str = "") -> None:
        cls.memory_mode = False
        cls.go_next = False

        cls.messages = [{"role": "system", "content": base_prompt_system}]
        prompt_user = base_prompt_user + "\n<KNOWN_INFO> no saved data </KNOWN_INFO>"
        cls.messages.append({"role": "user", "content": prompt_user})

        if launch_objective:
            cls.memory_mode = True
            cls.base_user = base_prompt_user
            cls.next_step = {
                            "get data": "modifie", "modifie": "test",
                            "test": "clean memory", "clean memory": "reset"}
            cls.current_step = "get data"
            cls.hints: list[str] = []

    @classmethod
    def apply_buffer(cls) -> None:
        cls.add_message(cls._msg_buffer)
        cls._msg_buffer = ""

    # Spceial Method usable by the llm
    @classmethod
    def save_missing_info(cls, msg: str) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")

        if hint in cls.hints:
            print("hint already knowed")
            # TODO IMPLEMENT ERROR CHECKING

        cls.hints.append(hint)
        print("hint saved")
        cls.save_data()

    # Spceial Method usable by the llm
    @classmethod
    def go_next_step(cls) -> None:
        if not cls.memory_mode:
            raise MemoryPromptError("Memory mode not configured")
        cls.go_next = True

    @classmethod
    def apply_go_next_step(cls) -> None:
        if not cls.go_next:
            return
        cls.go_next = False

        cls.current_step = cls.next_step[cls.current_step]
        print(f"step is now: {cls.current_step}")
        cls.save_data()

    
    """ 
    problematic:
        1 create a efficient memory manager for prompting
        2 how guide the llm to resolve the problem

    NEW PIEPLINE : 
    Idea 1:
        prompt rolling: 3 phases (3 prompt possible)
            1:
                get data
            2:
                modifie something
            3:
                test
            then:
                RESET THE ENVIRONEMENT
                CLEAN THE PROMPT
                new hint created !

        how switch phase:
            llm using tool next_phase()
            error detected:
                infinite repetition
                too many tokens used
                
        possible problems:
            large infinite loop using the rolling system
            prompt too large

    SPECIAL TOOLS:
        go_next_phase() ???
        save_hint(msg: str) ???

    possible prompt structure:
        1:
            system : all basics
            user:
                phase prompt
                MEMORY:
                    <hint>
                    <hint>
                    <output1>
                    <output2>
                    ...
    """ 

    @classmethod
    def compress_memory(cls) -> None:
        
        if cls.current_step != "clean memory":
            return
        cls.current_step = "get data"

        cls.messages = cls.messages[:2]
        cls.messages[1]["content"] = cls.base_user + "\n<KNOWN_INFO>\n"
        for i, elem in enumerate(cls.hints, 1):
            cls.messages[1]["content"] += f"[{i}] {elem}\n"
        cls.messages[1]["content"] += "</KNOWN_INFO>"

        

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
