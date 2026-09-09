import httpx
import json

URL = "http://127.0.0.1:8042/"


TESTS = [
    # read_file TESTS --------------------------------------------------------------------------------------------------------------
    ("POST", "/",
"""
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "read_file",
    "arguments": {"filepath": "test.py"},
    "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": 1}}
}
"""
    , 200,
r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "1: \n2: class Matchalate:\n3: \n4:     def __init__():\n5:         pass\n6: \n7:     def helo():\n8:         pass\n9: \n10: \n11: class CloakStyle:\n12: \n13:     def wear():\n14:         pass\n15: \n16:     def compare():\n17:         pass\n18: \n19: \n20: def goodbye():\n21:     pass\n22: \n23: \n24: def helo():\n25:     pass\n26: \n27: \n28: def compare():\n29:     pass\n30: \n31: \n32: # one\n33: # two\n34: # tree\n35: # four\n36: # five\n"}]}}'),

    ("POST", "/",
"""
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "read_file",
    "arguments": {"filepath": "test.py", "start_line": 3, "end_line": 7},
    "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": 1}}
}
"""
    , 200,
r'{"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "content": [{"type": "text", "text": "3: \n4:     def __init__():\n5:         pass\n6: \n7:     def helo():\n"}]}}'),

    # read_file TESTS --------------------------------------------------------------------------------------------------------------
]

def format_text(txt: str) -> str:
    return json.dumps(json.loads(txt))

def run_test(
    client: httpx.Client,
    method: str,
    path: str,
    request_text: str,
    expected_status: int,
    expected_text: str,
) -> bool:

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
        print(f"🟩 {method} {path}")
    else:
        print(f"🟥 {method} {path}")
        print(f"[request]  : {request_text}")
        print(f"[expected] : {expected_status} |{expected_text}|")
        print(f"[received] : {response.status_code} |{response.text}|")

    return success


def main():
    passed = 0

    with httpx.Client() as client:
        for test in TESTS:
            if run_test(client, *test):
                passed += 1

    print()
    print(f"{passed}/{len(TESTS)} tests passed")


if __name__ == "__main__":
    main()
