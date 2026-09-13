import httpx
import json
import os
from typing import Any


URL = "http://127.0.0.1:8042/"


TESTS = [

    # EDIT_FILE AND READFILE TESTS --------------------------------------------------------------------------------------------------------------
    # test 1-2 --------------------------------------------------------------------------------------------------------------
    (
        "classic : edit_file",
        {"name": "edit_file", "arguments": {"filepath": "test_dir/test.py", "old_str": "helo", "new_str": "goodbye"}}
        ,
        r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "file writed"}]}}'
    ),
    (
        "clasic : read_file",
        {"name": "read_file", "arguments": {"filepath": "test_dir/test.py"}}
        ,
r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "1: \n2: class Matchalate:\n3: \n4:     def __init__(self):\n5:         pass\n6: \n7:     def goodbye(self):\n8:         pass\n9: \n10: \n11: class CloakStyle:\n12: \n13:     def wear(self):\n14:         pass\n15: \n16:     def compare(self):\n17:         pass\n18: \n19: \n20: def muffin():\n21:     pass\n22: \n23: \n24: def goodbye():\n25:     pass\n26: \n27: \n28: def compare():\n29:     pass\n30: \n31: \n32: # one\n33: # two\n34: # tree\n35: # four\n36: # five\n"}]}}'
    ),

    # test 3-4 --------------------------------------------------------------------------------------------------------------
    (
        "edit back : edit_file",
        {"name": "edit_file", "arguments": {"filepath": "test_dir/test.py", "old_str": "goodbye", "new_str": "helo"}}
        ,
        r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "file writed"}]}}'
    ),

    (
        "read precise lines : read_file",
        {"name": "read_file", "arguments": {"filepath": "test_dir/test.py", "start_line": 3, "end_line": 7}}
        ,
r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "3: \n4:     def __init__(self):\n5:         pass\n6: \n7:     def helo(self):\n"}]}}'
    ),
    # test 5-7 --------------------------------------------------------------------------------------------------------------
    (
        "no file found : edit_file",
        {"name": "edit_file", "arguments": {"filepath": "noway.txt", "old_str": "this", "new_str": "to"}}
        ,
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: [Errno 2] No such file or directory: 'noway.txt'"}], "isError": true}}"""
    ),
    (
        "no string found : edit_file",
        {"name": "edit_file", "arguments": {"filepath": "test_dir/test.py", "old_str": "nowayifoundthis", "new_str": "to"}}
        ,
        r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: old_str not found in the file"}], "isError": true}}'
    ),
    (
        "no file found : read_file",
        {"name": "read_file", "arguments": {"filepath": "noway.txt"}}
        ,
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: [Errno 2] No such file or directory: 'noway.txt'"}], "isError": true}}"""
    ),
    
    # LIST_FILES TESTS --------------------------------------------------------------------------------------------------------------
    # test 8-9 --------------------------------------------------------------------------------------------------------------

    (
        "classic : list_files",
        {"name": "list_files", "arguments": {"directory": "test_dir/dir1"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "test_dir/dir1/four_ln <link>\ntest_dir/dir1/one.cpp <file>\ntest_dir/dir1/three_dir <dir>\ntest_dir/dir1/tour.txt <file>\n"}]}}"""
    ),
    (
            "pattern : list_files",
            {"name": "list_files", "arguments": {"directory": "test_dir/dir1", "pattern": "ou"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "test_dir/dir1/four_ln <link>\ntest_dir/dir1/tour.txt <file>\n"}]}}"""
    ),

    # SEARCH_CODE TESTS --------------------------------------------------------------------------------------------------------------
    # test 10-11 --------------------------------------------------------------------------------------------------------------

    (
        "classic : search_code",
        {"name": "search_code", "arguments": {"pattern": '	while (i < 10)\n	{\n		printf("%d hello", i);\n	}'}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "__OS_PATH_ABSOLUTE/test_dir/dir1/four_ln:8 \twhile (i < 10)\n__OS_PATH_ABSOLUTE/test_dir/dir1/four_ln:9 \t{\n__OS_PATH_ABSOLUTE/test_dir/dir1/four_ln:10 \t\tprintf(\"%d hello\", i);\n__OS_PATH_ABSOLUTE/test_dir/dir1/four_ln:11 \t}\n__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:8 \twhile (i < 10)\n__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:9 \t{\n__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:10 \t\tprintf(\"%d hello\", i);\n__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:11 \t}\n"}]}}"""
    ),
    (
        "precise : pattern search_code",
        {"name": "search_code", "arguments": {"pattern": '	while (i < 10)\n	{\n		printf("%d hello", i);\n	}', "file_pattern": "one"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:8 \twhile (i < 10)\n__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:9 \t{\n__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:10 \t\tprintf(\"%d hello\", i);\n__OS_PATH_ABSOLUTE/test_dir/dir1/one.cpp:11 \t}\n"}]}}"""
    ),

    # SEARCH_FUNCTION_OR_CLASS_DEFINITION_IN_CODE TESTS --------------------------------------------------------------------------------------------------------------
    # test 12 --------------------------------------------------------------------------------------------------------------
    (
        "basic search: search_function_or_class_definition_in_code",
        {"name": "search_function_or_class_definition_in_code", "arguments": {"name": "helo"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/dir1/one.cpp:19 void helo(char *msg)\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/dir1/one.cpp:24 class helo\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/test.py:7     def helo(self):\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/test.py:24 def helo():\n"}]}}"""

    ),

    # FIND_REFERENCES TESTS --------------------------------------------------------------------------------------------------------------
    # test 13-15 --------------------------------------------------------------------------------------------------------------
    (
        "line but no path : find_references",
        {"name": "find_references", "arguments": {"name": "banana", "line": 1}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: line argument need a filepath setted"}], "isError": true}}"""

    ),
    (
        "no path /python: find_references",
        {"name": "find_references", "arguments": {"name": "banana", "filepath": "heloworld.py", "line": 1}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: [Errno 2] No such file or directory: 'heloworld.py'"}], "isError": true}}"""

    ),
    (
        "no path /other : find_references",
        {"name": "find_references", "arguments": {"name": "banana", "filepath": "heloworld.c", "line": 1}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: [Errno 2] No such file or directory: 'heloworld.c'"}], "isError": true}}"""

    ),

    # test 16-18 --------------------------------------------------------------------------------------------------------------
    (
        "no func-class /other: find_references",
        {"name": "find_references", "arguments": {"name": "banana"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: no definition found"}], "isError": true}}"""

    ),
    (
        "no func/class /python : find_references",
        {"name": "find_references", "arguments": {"name": "noway", "filepath": "test_dir/ref_test_dir/one.py"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: name not found in file"}], "isError": true}}"""
    ),
    
    (
        "valid only name /other : find_references",
        {"name": "find_references", "arguments": {"name": "usage"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/ref_test_dir/three.cpp:7 \tobj.usage();\n\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/ref_test_dir/two.py:5 obj.usage()\n\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/ref_test_dir/two.py:7 usage()\n\n"}]}}"""

    ),

    # test 19-22 --------------------------------------------------------------------------------------------------------------
    (
        "wrong line /pyhton : find_references",
        {"name": "find_references", "arguments": {"name": "usage", "filepath": "test_dir/ref_test_dir/one.py", "line": 1}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: name not found in file at the given line"}], "isError": true}}"""

    ),

    (
        "wrong line /other : find_references",
        {"name": "find_references", "arguments": {"name": "usage", "filepath": "test_dir/ref_test_dir/five.hpp", "line": 2}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "error encounter: name not found in file at the given line"}], "isError": true}}"""
    ),
    (
        "python precise /python : find_references",
        {"name": "find_references", "arguments": {"name": "usage", "filepath": "test_dir/ref_test_dir/one.py", "line": 10}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/ref_test_dir/two.py:5 \n"}]}}"""

    ),

    (
        "other precise /other: find_references",
        {"name": "find_references", "arguments": {"name": "usage", "filepath": "test_dir/ref_test_dir/four.cpp", "line": 4}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/ref_test_dir/three.cpp:7 \tobj.usage();\n\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/ref_test_dir/two.py:5 obj.usage()\n\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/ref_test_dir/two.py:7 usage()\n\n"}]}}"""
    ),


    # RUN_TESTS TESTS --------------------------------------------------------------------------------------------------------------
    # test 23 --------------------------------------------------------------------------------------------------------------
    (
        "run the script -!TODO PLACEHOLDER SCRIPT USAGE!- : run_tests",
        {"name": "run_tests"},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "script launch\n"}]}}"""
    ),
    (
        "get git patch : get_patch",
        {"name": "get_patch"},
        r"""_SPECIAL_CHECK<cut-flag>git diff"""

    ),
    (
        "run a command : run_command",
        {"name": "run_command", "arguments": {"command": "ls", "workdir": "test_dir"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "dir1\nref_test_dir\ntest.py\ntest.sh\n"}]}}"""
    ),



    # x TESTS --------------------------------------------------------------------------------------------------------------
    # test 0 --------------------------------------------------------------------------------------------------------------

    # TEST 0 test structure ---!!!---
    (
        "",
        {"name": "", "arguments": {"": ""}},
        r"""{}"""

    ),
    # s/\/home\/abenabde\/Documents\/M5\/AgentSmith\/Dev_mcp_servers/__OS_PATH_ABSOLUTE/g
]

# HTTP-----------------------------------------------------------------------------------------------------------------------------------------------------------------

PAD = len(str(len(TESTS))) * " "

def format_text(txt: str) -> str:
    return json.dumps(json.loads(txt))

def run_test(
    client: httpx.Client,
    test_name,
    request_adds: dict[str, Any],
    expected_text: str,
) -> bool:

    base: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": None}}
    }
    base["params"].update(request_adds)
    request_text = f"{json.dumps(base)}"
    expected_text = expected_text.replace("__OS_PATH_ABSOLUTE", os.path.abspath("."))
    method = "POST"
    path = "/"
    expected_status = 200

    response = client.request(
        method,
        URL + path,
        content=request_text,
    )
   
    special_check = expected_text.startswith("_SPECIAL_CHECK")
    if special_check:
        check = expected_text.split("<cut-flag>")
        response_data = json.loads(response.text)
        match check[1]:
            case "git diff":
                success = response_data["result"]["content"][0]["text"].startswith("diff --git")
    else:
        success = (
            response.status_code == expected_status
            and format_text(response.text) == format_text(expected_text)
        )

    if success:
        print(f"🟩 {test_name}")
    else:
        print(f"🟥 {test_name}")
        print(f"[request]  : {request_text}")
        print(f"[expected] : {expected_status} |{expected_text}|")
        print(f"[received] : {response.status_code} |{response.text}|")

    return success


def main():
    if os.path.basename(os.path.abspath(".")) != "Dev_mcp_servers":
        print("Please launch tests in the 'Dev_mcp_servers' dir")
        return

    passed = 0

    with httpx.Client() as client:
        for i, test in enumerate(TESTS[:-1], 1):
            print(PAD[len(str(i)):], f"{i}:", end="")
            if run_test(client, *test):
                passed += 1

    print()
    print(f"{passed}/{len(TESTS) - 1} tests passed")

# STDIO-----------------------------------------------------------------------------------------------------------------------------------------------------------------

import subprocess

def run_test_stdio(
    process: subprocess.Popen,
    test_name,
    request_adds: dict[str, Any],
    expected_text: str,
) -> bool:

    base: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": None}}
    }
    base["params"].update(request_adds)
    request_text = f"{json.dumps(base)}"
    expected_text = expected_text.replace("__OS_PATH_ABSOLUTE", os.path.abspath("."))
    expected_status = 200  # conservé pour cohérence d'affichage, pas utilisé en stdio

    # Envoie la requête sur stdin (une ligne = un message JSON-RPC)
    try:
        process.stdin.write(request_text + "\n")
        process.stdin.flush()
    except BrokenPipeError:
        print(f"🟥 {test_name}")
        print(f"[error] : process died before write. stderr : {process.stderr.read()}")
        return False

    # Lit la réponse sur stdout (une ligne attendue)
    response_text = process.stdout.readline()

    if not response_text:
        print(f"🟥 {test_name}")
        print(f"[error] : empty response (process likely died). stderr : {process.stderr.read()}")
        return False

    special_check = expected_text.startswith("_SPECIAL_CHECK")
    if special_check:
        check = expected_text.split("<cut-flag>")
        response_data = json.loads(response_text)
        match check[1]:
            case "git diff":
                success = response_data["result"]["content"][0]["text"].startswith("diff --git")
    else:
        success = (
            format_text(response_text) == format_text(expected_text)
        )

    if success:
        print(f"🟩 {test_name}")
    else:
        print(f"🟥 {test_name}")
        print(f"[request]  : {request_text}")
        print(f"[expected] : |{expected_text}|")
        print(f"[received] : |{response_text}|")

    return success


def main_stdio():
    if os.path.basename(os.path.abspath(".")) != "Dev_mcp_servers":
        print("Please launch tests in the 'Dev_mcp_servers' dir")
        return

    process = subprocess.Popen(
        ["uv", "run", "python", "-u", "mcp_tools_swebench.py", "stdio"],
        env={**os.environ, "MCP_MODE": "stdio", "PYTHONUNBUFFERED": "1"},
        stdin=subprocess.PIPE,
        stdout=None,   # hérite du terminal actuel, pas de capture
        stderr=None,   # hérite du terminal actuel, pas de capture
        text=True,
        bufsize=1,
    )

    import time

    for i, test in enumerate(TESTS[:-1], 1):
        test_name, request_adds, expected_text = test

        base: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": None}}
        }
        base["params"].update(request_adds)
        request_text = json.dumps(base)

        print(f"--- envoi test {i} : {test_name} ---")
        try:
            process.stdin.write(request_text + "\n")
            process.stdin.flush()
        except BrokenPipeError:
            print(f"[error] : process died before write for test {i}")
            break

        time.sleep(0.3)  # laisse le temps au serveur d'écrire sa réponse dans le terminal

    try:
        process.stdin.close()
    except BrokenPipeError:
        pass
    process.terminate()
    process.wait()


if __name__ == "__main__":
    #main()
    main_stdio()
