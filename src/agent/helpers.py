
from openai import OpenAI
import os
import sys
import json
import subprocess
from dotenv import load_dotenv
import re


class Log:
    logs: str = ""
    log: dict[str, str] = dict()

    @classmethod
    def add_logs(cls, add: str) -> None:
        cls.logs += f"{add}\n"

    @classmethod
    def get_logs(cls) -> str:
        return cls.logs

    @classmethod
    def print_logs(cls) -> None:
        print(cls.logs, file=sys.stderr)

    @classmethod
    def add_log(cls, add: str, log_type: str) -> None:
        if cls.log.get(log_type):
            cls.log[log_type] += f"{add}\n"
        else:
            cls.log[log_type] = f"{add}\n"

    @classmethod
    def get_log(cls, log_type) -> str:
        return cls.log[log_type]

    @classmethod
    def get_all_log(cls) -> dict[str, str]:
        return cls.log

    @classmethod
    def print_log(cls, log_type: str) -> None:
        print(cls.log[log_type], file=sys.stderr)

    @classmethod
    def print_all_log(cls) -> None:
        print(cls.log, file=sys.stderr)


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
            raise LlmApiError(f"can't load providers in: {providers_file} error: {e}")
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
                params = { # temp for msg TODO
                    "model": self.urls[self.iurl]["models"][self.imodel],
                    "messages": msg
                }
                
                self.requests += 1
                response = self.urls[self.iurl]["client"].chat.completions.create(**params)
                return {
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

class MemoryError(Exception):
    pass

class BasePrompts:

    @classmethod
    def get_first_prompts(cls, function_definition: str, task_definition: str, test_imports: list[str],
                                test_list: list[str]) -> tuple[str, str]:
        system_prompt = (
                "You are a python coding agent "
                "specialised to resolve MBPP problems. "
                "You need to resolve Mostly Basic Python Problems. "
                "Create the function demanded by the user with the associed requirements all in python. "
                "Only code is important the user will not read your comments.\n"
                "You are in a fully automated pipeline, all the code you give is used in a sandbox and the output is returned by the user. "
                "For security the sandbox is a minimal python environnement, if the code not work, think of trying differents possibilities. "
                "Code executed in the sandbox have direct access to MCP-Tools functions for specials needs.\n"
                "So all the code you give, including Mcp-Tools usage need to be in python code block:\n```python\n<CODE>\n```\n"
                "Do not use python code block inside python code block !\n"
                "FOR END RESOLVING USE THE FOLLOWING FUNCTION WITH THE CODE AS ARGUMENT :\n"
                "```python\nfinal_answer(code: str)\n```\n"
                "For more you have important specials functions to manage your memory, helping for problem researchs and flaw tracking:\n"
                "```python\nset_new_current_objective(self, msg: str, old_objective_status: str)\n```\n"
                "```python\nadd_main_objective_hint(msg: str)\n```\n"
                "```python\nadd_current_objective_hint(msg: str)\n```\n"
                "Theses functions have automated XML management\n"
        )
        user_prompt = (
                    "<MAIN_OBJECTIVE>\n"
                    f"You need to create a python function, "
                    f"Description: {task_definition}\n"
                    f"Function definition: {function_definition}"
        )
#        if test_imports:  # TODO imports are a tet to do after code ???
#            user_prompt += "Premade imports of the environement are: {test_imports}\n"
        if test_list:
            user_prompt += f"Python assertion(s) need to pass: {test_list}\n"

        # TODO use good tools
        command = ["uv", "run", "sandbox", "--manual", "--mcp-stdio", "uv run python mcp_tools_swebench.py"]
        result = subprocess.run(
            command,
            cwd=".",
            capture_output=True,
            text=True,
        )
        user_prompt += str(result.stdout) + "\n"
        user_prompt += "</MAIN_OBJECTIVE>\n"
        user_prompt += f"<CURRENT_OBJECTIVE>{BasePrompts.get_first_objective()}</CURRENT_OBJECTIVE>"
        return (system_prompt, user_prompt)

    @classmethod
    def get_aftercode_prompt(cls, sandbox_output: str) -> str:
        out = f"{sandbox_output}\n"
        return out

    @classmethod
    def get_nocode_prompt(cls) -> str:
        out = "Now you thought about the problem, use code and eventually tools to continue the searches\n"
        return out

    @classmethod
    def get_first_objective(cls) -> str:
        out = "Find a new current objective or resolve the main one directly"
        return out
    

class MemoryPrompt:

    def __init__(self, base_prompt_system: str, base_prompt_user: str) -> None:
        self.max = 0
        self.true_max = 0
        self.current_objective = BasePrompts.get_first_objective()

        # tuples of (pos in messages, pos first car in message)
        self.main_hints: list[tuple[int, int]] = []
        self.current_hints: list[tuple[int, int]] = []

        self.messages = [{"role": "system", "content": base_prompt_system}]
        self.messages.append({"role": "user", "content": base_prompt_user})
        self.base_len = 2

    # Spceial Method usable by the llm
    def add_main_objective_hint(self, msg: str) -> None:

        message = self.messages[-1]
        if message["role"] != "assistant":
            raise MemoryError("last message not from assistant, can't add main hint")
        self.main_hints.append((len(self.messages) - 1, len(message["content"])))
        message["content"] += f"\n<MAIN_HINT>{msg}</MAIN_HINT>"

    # Spceial Method usable by the llm
    def add_current_objective_hint(self, msg: str) -> None:

        message = self.messages[-1]
        if message["role"] != "assistant":
            raise MemoryError("last message not from assistant, can't add current hint")
        self.current_hints.append((len(self.messages) - 1, len(message["content"])))
        message["content"] += f"\n<CURRENT_HINT>{msg}</CURRENT_HINT>"

    # Spceial Method usable by the llm
    def set_new_current_objective(self, msg: str, old_objective_status: str) -> None:

        main_hint = f"{self.current_objective}<STATUS:>{old_objective_status}"
        self.add_main_objective_hint(main_hint)
        self.current_objective = msg

    # if len(all_memory) > self.max + len(important_memory) ...
    # if len(all_memory) > self.true_max ...
    def compress_memory(self) -> None:
        # TODO
        pass

    def get_messages(self) -> list[dict[str, str]]:
        return self.messages

    def add_message(self, msg: str, role: str = "user") -> None:
        self.messages.append({"role": role, "content": msg})

    def get_message_codes(self, model: str) -> list[str]:
        # TODO

        out = []
        message = self.messages[-1]
        if message["role"] != "assistant":
            raise MemoryError("last message not from assistant, can't extract code")
        data = message["content"]
        match model:
            case "test":
                pass
            case "test2":
                pass
            case _:
                try:
                    out = re.findall(r"```python\s*\n(.*?)```", data, flags=re.DOTALL)
                except Exception:
                    pass
        return out

