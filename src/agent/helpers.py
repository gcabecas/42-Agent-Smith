
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

    def __init__(self, providers_file: str, agent_prompt: str,
                    baseurl: str = "", basemodel: str = "") -> None:
        self.agent_msg = agent_prompt
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

    def response(self, msg: str, tokens: int) -> dict[str, str | int]:

        while 1:
            try:
                response = self.urls[self.iurl]["client"].chat.completions.create(
                        model=self.urls[self.iurl]["models"][self.imodel],
                        messages=[
                            {"role": "system", "content": self.agent_msg},
                            {"role": "agent", "content": msg}
                        ],
                        max_tokens=tokens
                )
                return {
                        "message": response.choices[0].message.content,
                        "usage": response.usage.completion_tokens
                }
            except Exception as e:
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
