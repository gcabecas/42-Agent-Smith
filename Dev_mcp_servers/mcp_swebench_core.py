
# USING MCP VERSION 2026-07-28

from typing import Any, Literal, Optional, Callable, Generator
import sys
import os
import json
from pydantic import BaseModel, model_validator
from flask import Flask, request, Response
from mcp_tools_core import McpToolsCore
#from flask_sock import Sock


# TOOLS ---------------------------------------//

from threading import Thread, Lock
import time

class SWETools(McpToolsCore):

    def __init__(self, *args, **kwargs) -> None:
        methods = {
                "read_file" : {"filepath": str, "start_line": int ,
                               "end_line": int, "_start_line_optional": True, "_end_line_optional": True},
                "edit_file" : {"filepath": str, "old_str": str, "new_str": str},
                "list_files" : {"directory": str, "pattern": str, "_pattern_optional": True},
                "search_code" : {"pattern": str, "file_pattern": str, "_file_pattern_optional": True},
                "search_function_or_class_definition_in_code" : {"name": str},
                "find_references" : {"name": str, "filepath": str, "line": int,
                                     "_filepath_optional": True, "_line_optional": True},
                "run_tests" : {},
                "get_patch" : {},
                "run_command" : {"command": str, "workdir": str, "_workdir_optional": True}
        }
        super().__init__(*args, methods=methods, **kwargs)
        self.model = """
        {
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "resultType": "complete",
    "tools": [
      {
        "name": "read_file",
        "description": "Read the content of a file with line numbers (like 'cat -n').",
        "inputSchema": {
          "type": "object",
          "properties": {
            "filepath": { "type": "string" },
            "start_line": { "type": "integer" },
            "end_line": { "type": "integer" }
          },
          "required": ["filepath"]
        }
      },
      {
        "name": "edit_file",
        "description": "Replace an exact string in a file with a new string.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "filepath": { "type": "string" },
            "old_str": { "type": "string" },
            "new_str": { "type": "string" }
          },
          "required": ["filepath", "old_str", "new_str"]
        }
      },
      {
        "name": "list_files",
        "description": "List files in a directory matching a given pattern.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "directory": { "type": "string" },
            "pattern": { "type": "string" }
          },
          "required": ["directory"]
        }
      },
      {
        "name": "search_code",
        "description": "Perform a grep-like search in the codebase.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "pattern": { "type": "string" },
            "file_pattern": { "type": "string" }
          },
          "required": ["pattern"]
        }
      },
      {
        "name": "search_function_or_class_definition_in_code",
        "description": "Find the definition of a function or a class.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "name": { "type": "string" }
          },
          "required": ["name"]
        }
      },
      {
        "name": "find_references",
        "description": "Find all usages of a symbol (function or class).",
        "inputSchema": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "filepath": { "type": "string" },
            "line": { "type": "integer" }
          },
          "required": ["name"]
        }
      },
      {
        "name": "run_tests",
        "description": "Execute the evaluation script.",
        "inputSchema": {
          "type": "object",
          "properties": {},
          "additionalProperties": false
        }
      },
      {
        "name": "get_patch",
        "description": "Retrieve the unified git diff of all changes made to the repository.",
        "inputSchema": {
          "type": "object",
          "properties": {},
          "additionalProperties": false
        }
      },
      {
        "name": "run_command",
        "description": "Execute a shell command in the specified working directory. Returns stdout, stderr, and exit code.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "command": { "type": "string" },
            "workdir": { "type": "string" }
          },
          "required": ["command"]
        }
      }
    ]
  }
}
        """

    def read_file(self, tid: int, filepath: str, start_line: int = -1, end_line: float | int = float("inf")) -> None:
        time.sleep(2)
        if start_line < 1:
            start_line = 1
        if start_line > end_line:
            self.message_complete(f"error encounter: start_line can't be bigger than end_line", tid, error=True)
            return
        try:
            i = 0
            read = ""
            with open(filepath, "r") as file:
                i += 1
                if end_line <= i <= start_line:
                    read += file.readline()
                self.message_complete(f"{read}", tid)
        except Exception as e:
            self.message_complete(f"error encounter: {e}", tid, error=True)


    def edit_file(self, tid, filepath, old_str, new_str):
        pass

    def list_files(self, tid, directory, pattern: str = ""):
        pass



    def search_code(self, tid, pattern, file_pattern: str = ""):
        pass

    def search_function_or_class_definition_in_code(self, tid, name):
        pass

    def find_references(self, tid, name, filepath: str = "", line: int = -1):
        pass



    def run_tests(self, tid):
        pass

    def get_patch(self, tid):
        pass

    def run_command(self, tid, command, workdir: str = ""):
        pass

