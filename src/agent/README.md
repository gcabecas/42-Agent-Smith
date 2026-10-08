# Agent_Smith — Agent

LLM agent that solves **MBPP** (write a Python function passing assertions) and **SWE-bench** (produce a `git diff` fixing an issue).
Loop: LLM answers with one Python code block → executed in a sandbox (with MCP tools) → output sent back to the LLM → repeat until the LLM calls `final_answer(...)`.

## Entry points

| Benchmark | Script |
|-----------|--------|
| MBPP | `agent_mbpp.py` |
| SWE-bench | `agent_swe.py` |

Both scripts take **the same arguments** (CLI via `fire`: `--arg-name value`). Only two defaults differ.

```bash
uv run python agent_mbpp.py --task-file mbpp_task.json
uv run python agent_swe.py  --task-file swebench_task.json --provider-url "https://openrouter.ai/api/v1" --model-name "model/name"
```

| Argument | Required | Default (MBPP / SWE) | Description |
|----------|:--------:|----------------------|-------------|
| `--task-file` | **Yes** | — | Task JSON (see formats below) |
| `--output` | No | `mbpp_solution.json` / `swebench_solution.json` | Solution JSON to write (must end with `.json`) |
| `--providers-file` | No | `config/mbpp_providers.json` / `config/swe_providers.json` | Providers config JSON |
| `--provider-url` | No* | `""` | Provider base URL to start with |
| `--model-name` | No* | `""` | Model to start with |

API keys are read from `.env` (variable names given by `api_key` in the providers file; `EXTRA_API_KEY` for a provider not in the file).

### Optional arguments: `--provider-url` / `--model-name`

**Both must be set together**, otherwise an `LlmApiError` is raised.

- **Neither set** → starts with the **last model of the last provider** in the providers file.
- **Both set**:
  - URL found in the file, model found → starts with that model.
  - URL found, model unknown → model is appended to that provider's list and used.
  - URL not found → a new provider (last in the list) is created with that model (key from `EXTRA_API_KEY`).

### Provider / model order and fallback

Providers and models are walked **from the end to the start of the lists**:

1. Start model = last model of the last provider (or the one chosen with the arguments).
2. On any API error → switch to the **previous model of the same provider**.
3. If it was the first model → go to the **previous provider, on its last model**.
4. If it was the first provider → **loop back** to the last provider's last model.
5. Retry, indefinitely (the count is stored in `retries` per step).

Example with the providers file `[google: [A], openrouter: [B], mistral: [C, D, E]]`:
`E → D → C → B → A → E → D → ...`

## JSON formats

### Providers file
```json
[
  {"name": "openrouter", "url": "https://openrouter.ai/api/v1",
   "models": ["qwen/qwen3-235b-a22b-2507"], "api_key": "OPENROUTER_API_KEY"},
  {"name": "mistral", "url": "https://api.mistral.ai/v1",
   "models": ["mistral-medium-3-5", "codestral-2508"], "api_key": "MISTRAL_API_KEY"}
]
```
`api_key` is the **name of the env variable**, not the key. Order matters (see above).

### MBPP task (input, flat object)
| Field | Type | Required |
|-------|------|:--------:|
| `task_id` | int | Yes |
| `task_definition` | str | Yes |
| `function_definition` | str | Yes |
| `test_imports` | list[str] | No (`[]`) |
| `test_list` | list[str] | Yes |

```json
{
  "task_id": 11,
  "task_definition": "Write a python function to remove first and last occurrence of a given character from the string.",
  "function_definition": "def remove_Occ(s, ch):",
  "test_imports": [],
  "test_list": ["assert remove_Occ(\"hello\",\"l\") == \"heo\""]
}
```

### SWE-bench task (input, flat object)
| Field | Type | Required |
|-------|------|:--------:|
| `instance_id` | str | Yes |
| `problem_statement` | str | Yes |
| `docker_image` | str | Yes |
| `eval_script` | str | Yes |
| `hints_text` | str | No (`""`) |
| `repo` | str | Yes |

```json
{
  "instance_id": "sympy__sympy-23534",
  "problem_statement": "...",
  "docker_image": "swebench/sweb.eval.x86_64.sympy_1776_sympy-23534:latest",
  "eval_script": "#!/bin/bash\n...",
  "hints_text": "",
  "repo": "sympy/sympy"
}
```

### Solution (output, same for both)
| Field | Description |
|-------|-------------|
| `task_id` | MBPP id (as string) or SWE `instance_id` |
| `benchmark` | `"mbpp"` or `"swebench"` |
| `success` | Agent's own belief it solved the task |
| `solution` | MBPP: function code — SWE: `git diff` |
| `iterations` | Number of loop iterations |
| `total_requests` | LLM requests, retries included |
| `total_input_tokens` / `total_output_tokens` | Token sums |
| `total_time_seconds` | Wall-clock time |
| `steps` | List of per-step metrics (below) |
| `system_prompt` | Full system prompt sent to the LLM |
| `error` | Error message or `null` |
| `timestamp` | ISO 8601 |

Each entry of `steps`: `step` (1-indexed), `input_tokens`, `output_tokens`, `request_time_ms`, `timestamp`, `api_url`, `model_name`, `llm_input`, `llm_output` (raw), `sandbox_input`, `sandbox_output`, `retries`.

## Requirements

- `uv`, `openai`, `pydantic`, `fire`, `pexpect`, `python-dotenv`; `uv run sandbox` available
- MBPP: `mcp_tools_mbpp.py` in the working directory
- SWE-bench: Docker running (image is pulled automatically)

## Notes

- Only the **first** Python block of each LLM answer is executed.
- No max-iteration limit: the loop ends only on `final_answer`.
- SWE-bench uses a memory mode (alternating `code` / `memorise` phases, hints + `<KNOWN_DATA>` compression).
- Logs: `logs/log.txt` (auto-suffixed `_1`, `_2`, ... if it exists).
