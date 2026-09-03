.PHONY: install run debug clean fclean lint lint-strict


install:
	uv sync

run:
	uv run python -m src.main

debug:
	uv run python -m pdb -m src.main


clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -prune -exec rm -rf {} +

fclean:
	$(MAKE) clean
	rm -rf .venv/ 

lint:
	uv run flake8 .
	uv run mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	uv run flake8 .
	uv run mypy . --strict