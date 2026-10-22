import fire


def mbpp() -> None:
    from src.agent.agent_mbpp_core import main

    fire.Fire(main)


def swebench() -> None:
    from src.agent.agent_swe_core import main

    fire.Fire(main)
