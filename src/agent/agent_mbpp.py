
from typing import Any
from helpers import Log, LlmApi, BasePrompts,  MemoryPrompt
from agent import Agent
import json

from pydantic import BaseModel, Field

""" MBPP
Implement an agent CLI interface
# 1. Dump a task
cd moulinette
uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json
# 2. Run your agent
cd ../student
uv run python -m agent_mbpp --task-file ../cache/mbpp_task.json \
--output ../cache/mbpp_solution.json \
--model-name "model/name" --provider-url "https://provider.api/v1"
# 3. Validate solution
cd ../moulinette
uv run moulinette_eval validate mbpp ../cache/mbpp_task.json \
../cache/mbpp_solution.json
"""

class MBPPTaskInput(BaseModel):
    """Input for MBPP task evaluation."""
    task_id: int
    task_definition: str
    function_definition: str
    test_imports: list[str] = Field(default_factory=list)
    test_list: list[str] = Field(default_factory=list)

class NewMBPPTaskInput(BaseModel):
    data: MBPPTaskInput


class MBPPAgent(Agent):

    task_definition: str
    function_definition: str
    test_imports: list[str] = Field(default_factory=list)
    test_list: list[str] = Field(default_factory=list)


def create_mbpp_agent(*, task_file: str, output: str = "mbpp_solution.json",
        providers_file: str = "mbpp_providers.json",
        provider_url: str = "", model_name: str = "") -> MBPPAgent:

    with open(task_file, "r") as file:
        mbpp_data = json.load(file)
    task = NewMBPPTaskInput(data=mbpp_data).data

    system_prompt, user_prompt = BasePrompts.get_first_prompts(task.test_imports, task.test_list)
    llmapi = LlmApi(providers_file, provider_url, model_name)
    prompt=MemoryPrompt(system_prompt, user_prompt)
    
    agent = MBPPAgent(
                task_id=str(task.task_id), benchmark="mbpp",
                system_prompt=system_prompt, output_path=output,
                task_definition=task.task_definition,
                function_definition=task.function_definition,
                test_imports=task.test_imports,
                test_list=task.test_list,
                llmapi=llmapi,
                prompt=prompt
    )
    return agent

import sys
import traceback
import fire


def main(*args: Any, **kwargs: Any) -> None:
    agent = create_mbpp_agent(**kwargs)
    try:
        check = True
        while check:
            check = agent.next_step()
    except Exception:
        print(traceback.format_exc())
    finally:
        pass

if __name__ == "__main__":
    try:
        fire.Fire(main)
    except Exception:
        print(traceback.format_exc())






# TEMPORARY LINES/CODE/DATA ------------------------------------------------------------------------------------\/

import os
import sys

def test_llmapi() -> None:
    try:
        obj1 = LlmApi("mbpp_providers.json", "kek", "")
        print(obj1.iurl)
    except Exception as e:
        print("\nt1", e)
    try:
        obj2 = LlmApi("mbpp_providers.json", "", "kek")
        print(obj2.iurl)
    except Exception as e:
        print("\nt2", e)

    obj3 = LlmApi("mbpp_providers.json", "kek", "model")
    print("\nt3", obj3)

    obj4 = LlmApi("mbpp_providers.json", "yyy", "model")
    print("\nt4", obj4)

    obj5 = LlmApi("mbpp_providers.json", "zzz", "5")
    print("\nt5", obj5)

    rep = obj4.response("mbpp_providers.json", "helo", 60)
    print("rep", rep)

#import json
#if __name__ == "__main__":
#    try:
#        test_llmapi()
#    except KeyboardInterrupt:
#        print(Log.get_logs())
#    except Exception as e:
#        print(Log.get_logs(), f"error: {e}")



# ------------------------- IDEAS ------------------------


"""

Your mandatory tools are only present when your own MCP
server is connected.


PROCESS

context idee / MEMORY :

problem !
ADD AGENT-INTERN TOOLS !?
edit buffer arg lignes n


    important_data:
        system_prompt
        main_objective
        current_objective
        hints
        tools

    assistant format:
        start with "<HINT:>" : very important data conterning the main problem 
        objective finish -> definitive log
        
        if len messages > (150 + important_memory) : sumarize important_memory + 1 to important_memory + 100;
        important_memory : important_hints, objectives data, system user , main goal ... + condensed memory


    messages=[
        {"role": "system", "content": self.agent_msg},
        {"role": "agent", "content": msg},
        {"role": "assistant", "content": msg},
        {"role": "agent", "content": msg},
        {"role": "assistant", "content": msg},
        ...
    ],
    mbpp: 
        errors
        hint_storage = ""


    swe:
        objectif
        errors
        hint_storage = ""





    -> ask llm use tool / generate code --
    llm-choose--(1)(2)

    (1) code_generated += llm_output
    if done -> try/execute -> else demand next code with current code in prompt still end
    -> give output to llm -(do it again or end)--
    
    (2) use tool
    -> give output to llm -(do it again or end)--

(2 type of message possible / 2 system prompt ?)





"""


