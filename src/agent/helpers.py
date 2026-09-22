
from openai import OpenAI
import os
import json


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

    def response(self, msg: list[dict[str, str | int]], tokens: int) -> dict[str, str | int]:

        retries = 0
        while 1:
            try:
                params = { # temp for msg TODO
                    "model": self.urls[self.iurl]["models"][self.imodel],
                    "messages": [
                        {"role": "system", "content": "you are an ia"},
                        {"role": "user", "content": "do code"}
                    ],
                    "max_tokens": tokens
                }

                response = self.urls[self.iurl]["client"].chat.completions.create(**params)
                return {
                        "llm_output": response.choices[0].message.content,
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens" response.usage.completion_tokens,
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
                print(msg, file=sys.stderr)
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


class MemoryPrompt:

    def __init__(self, base_prompt_system: str, base_prompt_user: str) -> None:
        self.max
        self.true_max

        # tuples of (pos in messages, pos first car in message)
        self.main_hints: list[tuple[int, int]] = []
        self.current_hints: list[tuple[int, int]] = []

        self.messages = [{"role": "system", "content": base_prompt_system}]
        msg = f"<CURRENT_OBJECTIVE>\n{base_prompt_user}\n<CURRENT_OBJECTIVE>\n"
        self.messages.append({"role": "user", "content": msg})
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
    def set_new_objective(self, msg: str, old_objective_status: str) -> None:
        # TODO
        self.add_main_objective_hint(self, "")
        pass

    # if len(all_memory) > self.max + len(important_memory) ...
    # if len(all_memory) > self.true_max ...
    def compress_memory(self) -> None:
        # TODO
        pass

    def get_messages(self) -> list[dict[str, str]]:
        return self.messages

    def add_message(self, msg: str) -> None:
        self.messages.append({"role": "user", "content": msg})

    def get_message_code(self, model: str) -> str:
        # TODO
        match model:
            case "":
                pass
            case "":
                pass
            case _:
                pass

