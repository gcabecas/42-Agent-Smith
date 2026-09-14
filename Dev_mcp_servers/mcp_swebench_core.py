
# USING MCP VERSION 2026-07-28

from typing import Any, Literal, Optional, Callable, Generator
import sys
import os
import subprocess
import json
from pathlib import Path
from pydantic import BaseModel, model_validator
from flask import Flask, request
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
                new_read = read.replace(old_str, new_str, 1)
            else:
                self.message_complete(f"error encounter: old_str not found in the file", tid, error=True)
                return
            with open(filepath, "w") as file:
                file.write(new_read)
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
            elems = sorted(os.listdir(directory))
            for elem in elems:
                if pattern:
                    if pattern in elem:
                        path = f"{directory}/{elem}"
                        if os.path.islink(path):
                            read += f"{path} <link>\n"
                        elif os.path.isdir(path):
                            read += f"{path} <dir>\n"
                        else:
                            read += f"{path} <file>\n"
                else:
                    path = f"{directory}/{elem}"
                    if os.path.islink(path):
                        read += f"{path} <link>\n"
                    elif os.path.isdir(path):
                        read += f"{path} <dir>\n"
                    else:
                        read += f"{path} <file>\n"

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
            files = sorted([f for f in Path(".").rglob("*") if f.is_file()])
            for true_file in files:
                file = str(true_file)
                if file_pattern and file_pattern not in file:
                    continue
                try:
                    f_read = ""
                    line = ""
                    with open(file, "r") as f_open:
                        line = f_open.readline()
                        while line:
                            f_read += line
                            line = f_open.readline()
                    pos = f_read.find(pattern)
                    if pos != -1:
                        patterns = pattern.split("\n")

                        n_line = f_read[:pos].count("\n")
                        lines = f_read.split("\n")
                        for elem in patterns:
                            read += f"{true_file.absolute()}:{n_line + 1} {lines[n_line]}\n"
                            n_line += 1

                except Exception as e:
                    # read += f"error in file {true_file.absolute()} : {e}\n"
                    pass
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 


    def search_codes_data(self, file: str) -> tuple[str, list[Any]] | None:

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
        return (f_read, list(matches))

    def search_function_or_class_definition_in_code(self, tid: int, name: str) -> None:
        self.operation_mutex.acquire()

        read = ""
        try:
            files = sorted([f for f in Path(".").rglob("*") if f.is_file()])
            for true_file in files:
                file = str(true_file)
                try:
                    tmp = self.search_codes_data(file)
                    if tmp is None:
                        continue
                    f_read, matches = tmp

                    lines = f_read.split("\n")
                    for _, captures in matches:
                        if "definition.function" in captures or \
                                "definition.class" in captures:
                            node = captures["name"][0]
                            func_name = node.text.decode()
                            if name == func_name:
                                n_ligne = node.start_point[0]
                                read += f"{true_file.absolute()}:{n_ligne + 1} {lines[n_ligne]}\n"

                except Exception as e:
                    # read += f"error in file {true_file.absolute()} : {e}\n"
                    pass
        except Exception as e:
            self.message_complete(f"internal error : {e}", tid, error=True) 
            return
        finally:
            self.operation_mutex.release()
        self.message_complete(read, tid) 

    def find_references(self, tid, name, filepath: str = "", line: int = -1):
        self.operation_mutex.acquire()
        """
        all:
            py:
                precise
            oth:
                large
        no file_path:
            error line arg need a filepath
        no file_path  no line
            large
        no line
            py:
                one ref:
                    precise
                multiple ref:
                    multiple-precise
            oth:
                large
        """

        read = ""
        try:
            if line >= 0 and not filepath:
                raise ValueError("line argument need a filepath setted")

            # 1 get according files data python/other
            if not filepath.endswith(".py"):
                if filepath:
                    try:
                        with open(filepath, "r") as f_open:
                            f_read = ""
                            content = f_open.readline()
                            j = 1
                            while content:
                                if line > 0 and j == line and name not in content:
                                    raise ValueError("name not found in file at the given line")
                                f_read += content
                                content = f_open.readline()
                                j += 1
                            if name not in f_read:
                                raise ValueError("name not found in file")
                    except Exception:
                        raise

                all_matches = []
                used_files = []
                files = sorted([f for f in Path(".").rglob("*") if f.is_file()])
                for true_file in files:
                    file = str(true_file)
                    try:
                        tmp = self.search_codes_data(file)
                        if tmp is None:
                            continue
                        _, matches = tmp
                        all_matches.append(matches)
                        used_files.append(true_file.absolute())
                    except Exception:
                        pass

                # 2 retrieve data
                i = 0
                count = 0
                for matches in all_matches:
                    for _, captures in matches:
                        if not("definition.function" in captures or \
                                "definition.class" in captures):
                            node = captures["name"][0]
                            func_name = node.text.decode()
                            if name == func_name:
                                count += 1
                                n_ligne = node.start_point[0]
                                content = ""
                                try:
                                    with open(used_files[i], "r") as f_open:
                                        j = 0
                                        while j < n_ligne + 1:
                                            content = f_open.readline()
                                            j += 1
                                    read += f"{used_files[i]}:{n_ligne + 1} {content}\n"
                                except Exception:
                                    pass
                    i += 1
                if count == 0:
                    raise ValueError("no definition found")
            else:
                # 2 retrieve data
                try:
                    tmp = self.search_codes_data(filepath)
                    if tmp is None:
                        raise ValueError(f"can't load tree-siter data of {filepath}")
                    _, matches = tmp
                except Exception as e:
                    raise


                # WORKIN -------------------------------------------------------
                # 2.5 find the position of the original (rows not in args, or not setted args)

                pos = -1
                refs = []
                for _, captures in matches:
                    if "definition.function" in captures or \
                            "definition.class" in captures:
                        node = captures["name"][0]
                        obj_name = node.text.decode()
                        if name == obj_name:
                            obj_line = node.start_point[0] + 1
                            if line < 0 or line == obj_line:
                                pos =  node.start_point[1]
                                refs.append((obj_line, pos))
                if not refs:
                    if line > 0:
                        raise ValueError("name not found in file at the given line")
                    else:
                        raise ValueError(f"name not found in file")

                # 3 trieve data
                project = jedi.Project(".")
                script = jedi.Script(path=filepath, project=project)
                for the_line, col in refs:
                    references = script.get_references(the_line, col)
                    for ref in references:
                        if ref.is_definition():
                            continue
                        content = ""
                        try:
                            with open(ref.module_path, "r") as f_open:
                                j = 0
                                while j < ref.line:
                                    content = f_open.readline()
                                    j += 1
                            read += f"{ref.module_path}:{ref.line} {content}\n"
                        except Exception as e:
                            pass

        except Exception as e:
            self.message_complete(f"error encounter: {e}", tid, error=True)
            return
        finally:
            self.operation_mutex.release()
        if not read:
            read = "no reference(s) found"
        self.message_complete(read, tid) 

    def run_tests(self, tid):
        self.operation_mutex.acquire()
        workdir = os.environ.get("TESTBED_PATH")
        if not workdir:
            workdir = "."

        read = ""
        try:
            result = subprocess.run(
                    "./test_dir/test.sh", # PLACEHOLDER SCRIPT TODO -!-!-!-!-!-!-!-!-!-!-!
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
        workdir = os.environ.get("TESTBED_PATH")
        if not workdir:
            workdir = "."
        read = ""
        try:
            repo = Repo(workdir, search_parent_directories=True)
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
        self.model = {
    "jsonrpc": "2.0",
    "id": 0,  # Placeholder for the JSON-RPC request id supplied by the MCP client.
    "result": {
        "resultType": "complete",
        "ttlMs": 86400000,
        "cacheScope": "private",
        "tools": [
            {
                "name": "read_file",
                "description": (
                    "Read part or all of a text file and return each selected line "
                    "prefixed with its 1-based line number. By default, reads from "
                    "the beginning of the file through the end."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Path to the file to read."
                        },
                        "start_line": {
                            "type": "integer",
                            "description": (
                                "1-based first line to return. Values below 1 are "
                                "treated as 1."
                            )
                        },
                        "end_line": {
                            "type": "integer",
                            "description": (
                                "1-based last line to return, inclusive. Defaults "
                                "to the end of the file."
                            )
                        }
                    },
                    "required": ["filepath"]
                }
            },
            {
                "name": "edit_file",
                "description": (
                    "Replace the first occurrence of an exact string in a file with another "
                    "string. Fails if the provided string is not found in the file."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Path to the file to modify."
                        },
                        "old_str": {
                            "type": "string",
                            "description": "Exact text to search for in the file."
                        },
                        "new_str": {
                            "type": "string",
                            "description": "Text that replaces every occurrence of old_str."
                        }
                    },
                    "required": ["filepath", "old_str", "new_str"]
                }
            },
            {
                "name": "list_files",
                "description": (
                    "List the entries directly inside a directory. Optionally "
                    "filter entries by requiring the pattern to appear in their "
                    "filename. Each entry is identified as a directory, symbolic "
                    "link, or regular file."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "Path to the directory to inspect."
                        },
                        "pattern": {
                            "type": "string",
                            "description": (
                                "Optional substring that must be present in the "
                                "entry name."
                            )
                        }
                    },
                    "required": ["directory"]
                }
            },
            {
                "name": "search_code",
                "description": (
                    "Search the repository recursively for an exact text pattern "
                    "and return the matching file paths and line locations. "
                    "Optionally restrict the search to paths containing a given "
                    "file pattern."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Exact text to search for."
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": (
                                "Optional substring that must be present in the "
                                "file path for the file to be searched."
                            )
                        }
                    },
                    "required": ["pattern"]
                }
            },
            {
                "name": "search_function_or_class_definition_in_code",
                "description": (
                    "Search the repository recursively for function and class "
                    "definitions whose declared name exactly matches the given "
                    "name. Returns the file path and line containing each match."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "Exact function or class name to look for."
                            )
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "find_references",
                "description": (
                    "Find usages of a function or class. For Python files, uses "
                    "Jedi for symbol-aware reference resolution; for other "
                    "supported source files, searches parsed symbol data. A "
                    "filepath and optional line can be supplied to identify the "
                    "specific definition to analyze."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the function or class whose usages should be found."
                        },
                        "filepath": {
                            "type": "string",
                            "description": (
                                "Optional source file containing the definition. "
                                "Required when line is specified."
                            )
                        },
                        "line": {
                            "type": "integer",
                            "description": (
                                "Optional 1-based line containing the definition "
                                "to analyze. Requires filepath."
                            )
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "run_tests",
                "description": (
                    "Run the repository's evaluation test script and return its "
                    "standard output. Uses TESTBED_PATH when it is defined; "
                    "otherwise runs from the current working directory."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            },
            {
                "name": "get_patch",
                "description": (
                    "Return the unified Git diff between the current working tree "
                    "and HEAD, showing all uncommitted changes in the repository. "
                    "Uses TESTBED_PATH when it is defined; "
                    "otherwise runs from the current working directory."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False
                }
            },
            {
                "name": "run_command",
                "description": (
                    "Execute a command in a specified working directory and return its "
                    "standard output. The command is parsed into arguments and is not "
                    "executed through a shell."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": (
                                "Command line to execute, including its arguments."
                            )
                        },
                        "workdir": {
                            "type": "string",
                            "description": (
                                "Optional working directory in which to execute "
                                "the command."
                            )
                        }
                    },
                    "required": ["command"]
                }
            }
        ]
    }
}
