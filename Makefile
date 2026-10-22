.PHONY: install clean fclean lint lint-strict


install:
	uv sync

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -prune -exec rm -rf {} +

fclean:
	$(MAKE) clean
	rm -rf .venv/

lint:
	uv run flake8 src --exclude=src/mcp_server/tests --extend-ignore=E203,E501,W503
	uv run python -m compileall -q agent_mbpp.py agent_swebench.py src

lint-strict:
	$(MAKE) lint
	uv run mypy src --strict
