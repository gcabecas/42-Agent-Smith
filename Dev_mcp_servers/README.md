
# Agent Smith — MCP Server

MCP server component used by **Agent Smith** to expose software-engineering tools through the Model Context Protocol.

The server currently implements:

* MCP protocol version `2026-07-28`
* JSON-RPC 2.0
* `tools/list`
* `tools/call`
* `server/discover`
* HTTP transport
* stdio transport

## Requirements

* Python `>= 3.10`
* `uv`
* Git

## Installation

Install the project dependencies with:

```bash
uv sync
```

## Usage

The server is instantiated through `launch_server()`.

Example application entry point:

```python
from mcp_server import launch_server
import os

host = os.environ.get("MCP_HOST", "0.0.0.0")
port = int(os.environ.get("MCP_PORT", "8042"))
mode = os.environ.get("MCP_MODE", "http")

app = launch_server("SWE", mode, host, port)
```

For an HTTP application, the returned Flask application can be served with Gunicorn:

```bash
uv run gunicorn -w 4 -b 0.0.0.0:8042 your_app:app
```

For stdio:

```bash
MCP_MODE=stdio uv run python your_app.py
```

## Configuration

| Variable       | Default           | Description                         |
| -------------- | ----------------- | ----------------------------------- |
| `MCP_MODE`     | `http`            | Transport mode: `http` or `stdio`   |
| `MCP_HOST`     | `0.0.0.0`         | HTTP bind address                   |
| `MCP_PORT`     | `8042`            | HTTP listening port                 |
| `TESTBED_PATH` | current directory | Working directory used by SWE tools |

`TESTBED_PATH` is used by tools that operate on the repository, such as `run_tests` and `get_patch`.

## MCP methods

The server supports the following methods:

### `tools/list`

Returns the tools exposed by the server and their input schemas.

Example request:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

### `tools/call`

Executes one of the available tools.

Example request:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {
      "filepath": "./src/main.py"
    },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

### `server/discover`

Returns the supported MCP protocol versions and server capabilities.

Example:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "server/discover"
}
```

Example response:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "resultType": "complete",
    "supportedVersions": [
      "2026-07-28"
    ],
    "capabilities": {
      "tools": {}
    }
  }
}
```

# Transports

## stdio

In stdio mode, JSON-RPC requests are read from standard input and responses are written to standard output.

Application logs and debugging output should be written to standard error so that stdout remains reserved for MCP messages.

Example:

```bash
MCP_MODE=stdio uv run python your_app.py
```

## HTTP

In HTTP mode, the server exposes a Flask application.

The MCP endpoint is:

```text
POST /
```

A `GET /` request returns `405 Method Not Allowed`.

Example:

```bash
uv run gunicorn -w 4 -b 0.0.0.0:8042 your_app:app
```

# Project structure

```text
.
├── mcp_server.py
├── mcp_tools_core.py
├── mcp_swebench_core.py
├── pyproject.toml
└── README.md
```

### `mcp_server.py`

Handles transport, JSON-RPC requests, validation, and MCP method dispatch.

### `mcp_tools_core.py`

Provides the shared MCP infrastructure:

* JSON-RPC message generation
* request validation
* tool argument validation
* asynchronous tool execution
* transport-specific response handling

### `mcp_swebench_core.py`

Provides the SWE tools and their MCP schemas.


# Available SWE tools

## `read_file`

Read a text file and return its content with 1-based line numbers.

Arguments:

| Name         | Type    | Required | Description                    |
| ------------ | ------- | -------: | ------------------------------ |
| `filepath`   | string  |      yes | Path to the file               |
| `start_line` | integer |       no | First line to return           |
| `end_line`   | integer |       no | Last line to return, inclusive |

When omitted, `start_line` defaults to `1` and `end_line` defaults to the end of the file.

Example:

```json
{
  "name": "read_file",
  "arguments": {
    "filepath": "./src/main.py",
    "start_line": 10,
    "end_line": 30
  }
}
```

## `edit_file`

Replace the **first occurrence** of an exact string in a file.

Arguments:

| Name       | Type   | Required | Description           |
| ---------- | ------ | -------: | --------------------- |
| `filepath` | string |      yes | Path to the file      |
| `old_str`  | string |      yes | Exact text to replace |
| `new_str`  | string |      yes | Replacement text      |

The operation fails when `old_str` is not found.

Example:

```json
{
  "name": "edit_file",
  "arguments": {
    "filepath": "./src/main.py",
    "old_str": "def hello():",
    "new_str": "def goodbye():"
  }
}
```

## `list_files`

List the entries directly contained in a directory.

An optional pattern filters entries by filename substring.

Each entry is reported as a directory, symbolic link, or regular file.

Arguments:

| Name        | Type   | Required | Description               |
| ----------- | ------ | -------: | ------------------------- |
| `directory` | string |      yes | Directory to inspect      |
| `pattern`   | string |       no | Filename substring filter |

Example:

```json
{
  "name": "list_files",
  "arguments": {
    "directory": "./src",
    "pattern": ".py"
  }
}
```

## `search_code`

Search recursively through the repository for an exact text pattern.

An optional `file_pattern` restricts the search to paths containing the given substring.

Arguments:

| Name           | Type   | Required | Description                                 |
| -------------- | ------ | -------: | ------------------------------------------- |
| `pattern`      | string |      yes | Exact text to search for                    |
| `file_pattern` | string |       no | Substring that must appear in the file path |

Example:

```json
{
  "name": "search_code",
  "arguments": {
    "pattern": "message_complete",
    "file_pattern": ".py"
  }
}
```

## `search_function_or_class_definition_in_code`

Search recursively for function or class definitions whose declared name exactly matches the requested name.

Arguments:

| Name   | Type   | Required | Description            |
| ------ | ------ | -------: | ---------------------- |
| `name` | string |      yes | Function or class name |

Example:

```json
{
  "name": "search_function_or_class_definition_in_code",
  "arguments": {
    "name": "McpToolsCore"
  }
}
```

## `find_references`

Find usages of a function or class.

For Python files, symbol references are resolved using Jedi. For other supported source files, the server uses parsed source information.

Arguments:

| Name       | Type    | Required | Description                            |
| ---------- | ------- | -------: | -------------------------------------- |
| `name`     | string  |      yes | Function or class name                 |
| `filepath` | string  |       no | File containing the definition         |
| `line`     | integer |       no | 1-based line containing the definition |

`line` requires `filepath`.

Example:

```json
{
  "name": "find_references",
  "arguments": {
    "name": "McpToolsCore",
    "filepath": "./mcp_tools_core.py",
    "line": 8
  }
}
```

## `run_tests`

Run the repository evaluation script:

```text
./test_dir/test.sh
```

The working directory is taken from `TESTBED_PATH` when defined, otherwise from the current working directory.

Arguments: none.

Example:

```json
{
  "name": "run_tests",
  "arguments": {}
}
```

## `get_patch`

Return the unified Git diff between the current working tree and `HEAD`.

The working directory is taken from `TESTBED_PATH` when defined, otherwise from the current working directory.

Arguments: none.

Example:

```json
{
  "name": "get_patch",
  "arguments": {}
}
```

## `run_command`

Execute a command in a specified working directory.

The command is parsed into arguments before execution and is not executed through a shell.

Arguments:

| Name      | Type   | Required | Description             |
| --------- | ------ | -------: | ----------------------- |
| `command` | string |      yes | Command line to execute |
| `workdir` | string |       no | Working directory       |

Example:

```json
{
  "name": "run_command",
  "arguments": {
    "command": "git status",
    "workdir": "."
  }
}
```

# References

* [MCP specification — 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
* [JSON-RPC](https://en.wikipedia.org/wiki/JSON-RPC)
* [Flask documentation](https://flask.palletsprojects.com/en/stable/quickstart/)
* [Gunicorn documentation](https://gunicorn.org/)
* [WSGI overview](https://python.plainenglish.io/tutorial-from-flasks-dev-server-to-production-with-apache-wsgi-6e986f404091)

