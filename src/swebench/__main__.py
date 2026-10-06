import argparse

from src.sandbox.cli import repl
from src.swebench.session import SweBenchSession, load_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="src.swebench")
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--python", default="python")
    parser.add_argument("--manual", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task = load_task(args.task_file)
    with SweBenchSession(task, args.python) as session:
        print(f"[task] {session.task.instance_id} ({session.task.repo})")
        print(f"[image] {session.task.docker_image}")
        sandbox = session.start()

        if args.manual:
            print(session.manual)
        else:
            repl(sandbox)

    print("[container] removed")


if __name__ == "__main__":
    main()
