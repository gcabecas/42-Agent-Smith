
import fire
import traceback

from src.agent.agent_mbpp_core import main


if __name__ == "__main__":
    try:
        fire.Fire(main)
    except Exception:
        print(traceback.format_exc())
