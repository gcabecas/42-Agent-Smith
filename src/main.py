import sys

from src.sandbox.config import load_config
from src.sandbox.execute import execute


def main() -> None:
    try:
        config = load_config("sandbox_template.json")

        with open("test_sandbox/imports.txt") as f:
            code = f.read()

        result = execute(code, config)
        print(result)
    except Exception as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
