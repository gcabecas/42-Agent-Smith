import httpx
import json
from typing import Any


URL = "http://127.0.0.1:8042/"


TESTS = [

    # EDIT_FILE AND READFILE TESTS --------------------------------------------------------------------------------------------------------------
    # test 1-2 --------------------------------------------------------------------------------------------------------------
    (
        "classic : edit_file",
        {"name": "edit_file", "arguments": {"filepath": "test.py", "old_str": "helo", "new_str": "goodbye"}}
        ,
        r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "file writed"}]}}'
    ),
    (
        "clasic : read_file",
        {"name": "read_file", "arguments": {"filepath": "test.py"}}
        ,
r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "1: \n2: class Matchalate:\n3: \n4:     def __init__():\n5:         pass\n6: \n7:     def goodbye():\n8:         pass\n9: \n10: \n11: class CloakStyle:\n12: \n13:     def wear():\n14:         pass\n15: \n16:     def compare():\n17:         pass\n18: \n19: \n20: def muffin():\n21:     pass\n22: \n23: \n24: def goodbye():\n25:     pass\n26: \n27: \n28: def compare():\n29:     pass\n30: \n31: \n32: # one\n33: # two\n34: # tree\n35: # four\n36: # five\n"}]}}'
    ),

    # test 3-4 --------------------------------------------------------------------------------------------------------------
    (
        "edit back : edit_file",
        {"name": "edit_file", "arguments": {"filepath": "test.py", "old_str": "goodbye", "new_str": "helo"}}
        ,
        r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "file writed"}]}}'
    ),

    (
        "read precise lines : read_file",
        {"name": "read_file", "arguments": {"filepath": "test.py", "start_line": 3, "end_line": 7}}
        ,
r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "3: \n4:     def __init__():\n5:         pass\n6: \n7:     def helo():\n"}]}}'
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
        {"name": "edit_file", "arguments": {"filepath": "test.py", "old_str": "nowayifoundthis", "new_str": "to"}}
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
        {"name": "list_files", "arguments": {"directory": "test_dir"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "test_dir/four_ln <link>\ntest_dir/one.cpp <file>\ntest_dir/three_dir <dir>\ntest_dir/tour.txt <file>\n"}]}}"""
    ),
    (
            "pattern : list_files",
            {"name": "list_files", "arguments": {"directory": "test_dir", "pattern": "ou"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "test_dir/four_ln <link>\ntest_dir/tour.txt <file>\n"}]}}"""
    ),

    # SEARCH_CODE TESTS --------------------------------------------------------------------------------------------------------------
    # test 10-11 --------------------------------------------------------------------------------------------------------------

    (
        "classic : search_code",
        {"name": "search_code", "arguments": {"pattern": '	while (i < 10)\n	{\n		printf("%d hello", i);\n	}'}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/four_ln:8 \twhile (i < 10)\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/four_ln:9 \t{\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/four_ln:10 \t\tprintf(\"%d hello\", i);\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/four_ln:11 \t}\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:8 \twhile (i < 10)\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:9 \t{\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:10 \t\tprintf(\"%d hello\", i);\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:11 \t}\n"}]}}"""
    ),
    (
        "precise : pattern search_code",
        {"name": "search_code", "arguments": {"pattern": '	while (i < 10)\n	{\n		printf("%d hello", i);\n	}', "file_pattern": "one"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:8 \twhile (i < 10)\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:9 \t{\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:10 \t\tprintf(\"%d hello\", i);\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:11 \t}\n"}]}}"""
    ),

    # SEARCH_FUNCTION_OR_CLASS_DEFINITION_IN_CODE TESTS --------------------------------------------------------------------------------------------------------------
    # test 12 --------------------------------------------------------------------------------------------------------------
    (
        "basic search: search_function_or_class_definition_in_code",
        {"name": "search_function_or_class_definition_in_code", "arguments": {"name": "helo"}},
        r"""{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test.py:7     def helo():\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test.py:24 def helo():\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:19 void helo(char *msg)\n/home/abenabde/Documents/M5/AgentSmith/Dev_mcp_servers/test_dir/one.cpp:24 class helo\n"}]}}"""

    ),

    # x TESTS --------------------------------------------------------------------------------------------------------------
    # test 0 --------------------------------------------------------------------------------------------------------------

    # TEST 0 test structure ---!!!---
    (
        "",
        {"name": "", "arguments": {"": ""}},
        r"""{}"""

    ),
]

def format_text(txt: str) -> str:
    return json.dumps(json.loads(txt))

def run_test(
    client: httpx.Client,
    test_name,
    request_adds: dict[str, Any],
    expected_text: str,
) -> bool:

    base = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": None}}
    }
    base["params"].update(request_adds)
    request_text = f"{json.dumps(base)}"
    method = "POST"
    path = "/"
    expected_status = 200

    response = client.request(
        method,
        URL + path,
        content=request_text,
    )

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
    passed = 0

    with httpx.Client() as client:
        for i, test in enumerate(TESTS[:-1], 1):
            print(f"{i}:", end="")
            if run_test(client, *test):
                passed += 1

    print()
    print(f"{passed}/{len(TESTS)} tests passed")


if __name__ == "__main__":
    main()
