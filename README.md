*This project has been created as part of the 42 curriculum by gcabecas, abenabde.*

# Agent Smith

## Description

Agent Smith is an autonomous Python coding agent for two evaluation tracks:

- **MBPP**: generate a Python function that satisfies a set of assertions;
- **SWE-bench**: inspect and modify a real repository inside a task-specific Docker container, run its evaluation script, and return a Git patch.

The project implements its own agent loop, sandbox, Model Context Protocol (MCP) client and MCP tool servers. It does not use an external agent-orchestration framework.

## Architecture

```text
.
├── agent_mbpp.py                 # Required MBPP module entry point
├── agent_swebench.py             # Required SWE-bench module entry point
├── mcp_tools_mbpp.py             # MBPP MCP server
├── mcp_tools_swebench.py         # SWE-bench MCP server
├── config/
│   ├── mbpp_providers.json
│   └── swe_providers.json
├── scripts/
│   └── run_all_evals.py          # Complete local evaluation runner
└── src/
    ├── agent/                     # Agent loop, prompts, providers and metrics
    ├── common/                    # Shared Pydantic task/config models
    ├── mcp_server/                # MCP transports and tool implementations
    ├── sandbox/                   # Restricted Python execution environment
    └── swebench/                  # Docker task testbed
```

The main responsibilities are separated as follows:

- the agent owns task loading, prompting, the reasoning loop and the final `SolutionOutput`;
- the sandbox executes LLM-generated Python under import, filesystem, time, memory and network restrictions;
- the MCP client discovers tools and makes them callable inside the sandbox;
- MCP servers execute privileged actions outside the sandbox security domain;
- `DockerTestbed` owns the SWE-bench container lifecycle and task repository.

## Agent loop

Both agents follow the same high-level cycle:

```text
task -> prompt -> LLM response -> code extraction -> sandbox execution
     -> observation -> next prompt -> ... -> final_answer
```

Each iteration records:

- input and output tokens;
- request duration, model and API endpoint;
- raw LLM output;
- code sent to the sandbox;
- sandbox output;
- retry count and timestamp.

MBPP validates candidate code against task assertions. SWE-bench uses MCP tools to inspect and edit the repository, execute the task evaluation script and retrieve the final patch.

## Sandbox design

The sandbox runs generated Python in a child process with:

- an explicit import allowlist;
- restricted file access;
- blocked network access;
- restricted builtins;
- execution time and memory limits;
- persistent state during an interactive sandbox session;
- dynamic MCP tool injection;
- the built-in `final_answer` control function.

The default configuration is defined by `SandboxConfig` and can be overridden with a JSON file.

## MCP tools

The MBPP server exposes:

- `run_tests(code, test_list)`.

The SWE-bench server exposes:

- `read_file`;
- `edit_file`;
- `list_files`;
- `search_code`;
- `search_function_or_class_definition_in_code`;
- `find_references`;
- `run_tests`;
- `get_patch`;
- `run_command`.

The sandbox supports MCP over stdio and streamable HTTP. Its manual is generated from the schemas returned by the connected server.

## Instructions

### Requirements

- Python 3.10;
- `uv`;
- Git;
- Docker for SWE-bench.

### Installation

```bash
uv sync --frozen
```

### API configuration

Create `src/agent/.env` and define the keys used by the provider configuration files. For example:

```dotenv
OPENROUTER_API_KEY=...
MISTRAL_API_KEY=...
GOOGLE_API_KEY=...
GROQ_API_KEY=...
```

The `.env` file is ignored by Git. Provider JSON files contain environment-variable names, never secret values.

### Run the sandbox

```bash
uv run sandbox
uv run sandbox sandbox_template.json
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
uv run sandbox --mcp-server http://localhost:8042
```

### Run MBPP

```bash
uv run python -m agent_mbpp \
  --task-file /path/to/mbpp_task.json \
  --output /path/to/mbpp_solution.json
```

Optional model selection:

```bash
uv run python -m agent_mbpp \
  --task-file /path/to/mbpp_task.json \
  --output /path/to/mbpp_solution.json \
  --model-name "model/name" \
  --provider-url "https://provider.example/v1"
```

### Run SWE-bench

Docker must be running before launching the agent.

```bash
uv run python -m agent_swebench \
  --task-file /path/to/swebench_task.json \
  --output /path/to/swebench_solution.json
```

The task file provides the Docker image, repository metadata, problem statement and evaluation script. One persistent container is used for the task and removed when the agent exits normally.

### Run project checks

```bash
make lint
uv run python -m compileall agent_mbpp.py agent_swebench.py src
```

### Run the complete local evaluation set

```bash
uv run python scripts/run_all_evals.py
```

The evaluation runner executes every selectable MBPP and SWE-bench task sequentially, applies hard process timeouts, stores per-task logs and validates each produced solution with the moulinette.

## Benchmark results and analysis

The latest official-style sample measured during development produced:

| Track | Result | Interpretation |
|---|---:|---|
| MBPP | 4/5 | Minimum pass threshold reached |
| SWE-bench | Not rerun after CLI cleanup | A new three-task run is required |
| Sandbox | 9/14 | Core execution works; remaining MCP/tool and security work is required |

Generated evaluation results are intentionally excluded from the submitted repository. The complete required multi-model study must be recorded in `BENCHMARK_REPORT.md` with its selected backing `solution.json` files before final submission.

## Resources

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [OpenAI Python library](https://github.com/openai/openai-python)
- [Pydantic documentation](https://docs.pydantic.dev/)
- [Docker SDK for Python](https://docker-py.readthedocs.io/)
- [SWE-bench](https://www.swebench.com/)
- [MBPP dataset paper](https://arxiv.org/abs/2108.07732)
- Python documentation for [`multiprocessing`](https://docs.python.org/3/library/multiprocessing.html) and [`resource`](https://docs.python.org/3/library/resource.html)

## Use of AI

AI assistance was used during development to:

- compare the implementation with the project specification;
- investigate failing evaluation traces;
- review sandbox and Docker lifecycle risks;
- identify cleanup, typing and packaging issues;
- help draft documentation and test procedures.

All generated suggestions were reviewed against the repository, executed where possible, and kept only when supported by source-code or runtime evidence.
