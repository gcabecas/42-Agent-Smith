
# USING MCP VERSION 2026-07-28

from typing import Any, Literal, Optional, Callable, Generator
import sys
import os
import subprocess
import json
from pathlib import Path
from pydantic import BaseModel, model_validator
from flask import Flask, request, Response
import tree_sitter_language_pack as tslp
import tree_sitter
from git import Repo
import jedi
import shlex

from mcp_tools_core import McpToolsCore

# TOOLS ---------------------------------------//

from threading import Thread, Lock
import time

class SWETools(McpToolsCore):

    def read_file(self, tid: int, filepath: str, start_line: int = -1, end_line: float | int = float("inf")) -> None:
        self.operation_mutex.acquire()
        
        read = ""
        try:
            if start_line < 1:
                start_line = 1
            if start_line > end_line:
                self.message_complete(f"error encounter: start_line can't be bigger than end_line", tid, error=True)
                return
            i = 0
            with open(filepath, "r") as file:
                line = file.readline()
                while line:
                    i += 1
                    if end_line >= i >= start_line:
                        read += f"{str(i)}: {line}"
                    line = file.readline()

        except Exception as e:
            self.message_complete(f"error encounter: {e}", tid, error=True)
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid)


    def edit_file(self, tid: int, filepath: str, old_str: str, new_str: str) -> None:
        self.operation_mutex.acquire()

        read = ""
        try:
            with open(filepath, "r") as file:
                line = file.readline()
                while line:
                    read += line
                    line = file.readline()
            if old_str in read:
                read.replace(old_str, new_str)
            else:
                self.message_complete(f"error encounter: old_str not found in the file", tid, error=True)
                return
            with open(filepath, "w") as file:
                file.write(read)
        except Exception as e:
            self.message_complete(f"error encounter: {e}", tid, error=True)
            return
        finally:
            self.operation_mutex.release()
        self.message_complete("file writed", tid)


    def list_files(self, tid: int, directory: str, pattern: str = "") -> None:
        self.operation_mutex.acquire()
        
        read = ""
        try:
            for elem in os.listdir(directory):
                if pattern:
                    if pattern in elem:
                        read += f"{elem}\n"
                else:
                    read += f"{elem}\n"
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 


    def search_code(self, tid: int, pattern: str, file_pattern: str = "") -> None:
        self.operation_mutex.acquire()
        
        read = ""
        try:
            files = [f for f in Path(".").rglob("*") if f.is_file()]
            for true_file in files:
                file = str(true_file)
                if file_pattern and file_pattern not in file:
                    continue
                try:
                    f_read = ""
                    with open(file, "r") as f_open:
                        line = f_open.readline()
                        while line:
                            f_read += line
                            line = f_open.readline()
                    pos = f_read.find(pattern)
                    if pos != -1:
                        n_line = read[:pos].count("\n")
                        lines = read.split("\n")
                        read += f"{true_file.resolve()}:{n_line + 1} {lines[n_line]}\n"
                except Exception as e:
                    read += f"error in file {true_file.resolve()} : {e}\n"
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 


    def search_codes_data(self, file: str) -> list[Any] | None:

        f_read = ""
        lang_key = tslp.detect_language(file)
        if lang_key is None or file.startswith("."):
           # read += f"'{file}' cannot detect language\n"
            return None

        with open(file, "r") as f_open:
            line = f_open.readline()
            while line:
                f_read += line
                line = f_open.readline()

        parser = tslp.get_parser(lang_key)
        if parser is None:
            return None
        language = tslp.get_language(lang_key)
        tree = parser.parse(f_read.encode("utf-8"))

        # Query
        query_string = tslp.get_tags_query(lang_key)
        if query_string is None:
            return None
        # Usable objet from query
        query = tree_sitter.Query(language, query_string)
        if query is None:
            return None
        # cursor to use query on tree
        cursor = tree_sitter.QueryCursor(query)
        # usage
        matches = cursor.matches(tree.root_node)
        return list(matches)

    def search_function_or_class_definition_in_code(self, tid: int, name: str) -> None:
        self.operation_mutex.acquire()

        read = ""
        try:
            files = [f for f in Path(".").rglob("*") if f.is_file()]
            for true_file in files:
                file = str(true_file)
                try:
                    matches = search_codes_data(file)
                    if matches is None:
                        continue

                    lines = f_read.split("\n")
                    for _, captures in matches:
                        if "definition.function" in captures or \
                                "definition.class" in captures:
                            node = captures["name"][0]
                            func_name = node.text.decode()
                            if name == func_name:
                                n_ligne = node.start_point[0]
                                read += f"{true_file.resolve()}:{n_ligne + 1} {lines[n_ligne]}\n"

                except Exception as e:
                    read += f"error in file {true_file.resolve()} : {e}\n"
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 

    def find_references(self, tid, name, filepath: str = "", line: int = -1):
        self.operation_mutex.acquire()

        read = ""
        try:
            if not filepath or not filepath.endswith(".py"):
                all_matches = []
                used_files = []
                pyfiles = [f for f in Path(".").rglob("*.py") if f.is_file()]
                files = [f for f in Path(".").rglob("*") if f.is_file() and not str(f).endswith(".py")]
                for elem in [pyfiles, files]:
                    for true_file in elem:
                        file = str(true_file)
                        try:
                            matches = search_codes_data(file)
                            if matches is None:
                                continue
                            all_matches.append(matches)
                            used_files.append(file)
                        except Exception:
                            pass
            else:
                matches = search_codes_data(filepath)
                if matches is None:
                    raise ValueError("can't load tree-siter data of a .py")
            
            i = 0
            pos = -1
            for matches in all_matches:
                for _, captures in matches:
                    if "definition.function" in captures or \
                            "definition.class" in captures:
                        node = captures["name"][0]
                        obj_name = node.text.decode()
                        if name == obj_name:
                            obj_line = node.start_point[0] + 1
                            if line == -1 or line == obj_line:
                                line = obj_line
                                pos =  node.start_point[1]
                                break
                i += 1
            if pos == -1:
                raise ValueError("name not found in file(s)")

            if filepath.endswith(".py") or used_files[i].endswith(".py"):

                project = jedi.Project(".")
                script = jedi.Script(path=filepath, project=project)
                definitions = script.goto(line, pos)
                references = definitions[0].usages()
                for ref in references:
                    read += f"{ref.module_path}:{ref.line} PLACEHERELINECONTENT"
            else:
                i = 0
                for matches in all_matches:
                    if used_files[i].endswith(".py"):
                        i += 1
                        continue
                    for _, captures in matches:
                        if not("definition.function" in captures or \
                                "definition.class" in captures):
                            node = captures["name"][0]
                            func_name = node.text.decode()
                            if name == func_name:
                                n_ligne = node.start_point[0]
                                read += f"{true_file.resolve()}:{n_ligne + 1} {lines[n_ligne]}\n"



        except Exception as e:
            self.message_complete(f"error encounter: {e}", tid, error=True)
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 

    def run_tests(self, tid):
        self.operation_mutex.acquire()

        time.sleep(10)
        read = ""
        try:
            result = subprocess.run(
                    "test",
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    check=True
            )
            read = str(result.stdout)
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 

    def get_patch(self, tid):
        self.operation_mutex.acquire()
        read = ""
        try:
            repo = Repo(".")
            read = repo.git.diff("HEAD")
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 

    def run_command(self, tid: int, command: str, workdir: str = "") -> None:
        self.operation_mutex.acquire()
        read = ""
        try:
            result = subprocess.run(
                    shlex.split(command),
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    check=True
            )
            read = str(result.stdout)
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 


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
