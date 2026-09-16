import httpx
import json

URL = "http://127.0.0.1:8042/"

META_OK = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {}
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def list_body(meta=None, extra_top=None):
    if meta is None:
        meta = META_OK

    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {
            "_meta": meta
        }
    }

    if extra_top:
        body["params"].update(extra_top)

    return body


def call_body(name="read_file", arguments=None, meta=None, extra_top=None):
    if meta is None:
        meta = META_OK

    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": name,
            "_meta": meta
        }
    }

    if arguments is not None:
        body["params"]["arguments"] = arguments

    if extra_top:
        body["params"].update(extra_top)

    return body


def discover_body(meta=None, extra_top=None):
    if meta is None:
        meta = META_OK

    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "server/discover",
        "params": {
            "_meta": meta
        }
    }

    if extra_top:
        body["params"].update(extra_top)

    return body


def headers_for_payload(payload):
    """
    Build valid HTTP/MCP headers automatically from a payload.

    Invalid payloads are intentionally handled conservatively:
    a malformed or missing field is not turned into an invalid HTTP header.
    """
    headers = {
        "Content-Type": "application/json"
    }

    if isinstance(payload, str):
        return headers

    if not isinstance(payload, dict):
        return headers

    params = payload.get("params")
    if not isinstance(params, dict):
        params = {}

    meta = params.get("_meta")
    if not isinstance(meta, dict):
        meta = {}

    protocol_version = meta.get(
        "io.modelcontextprotocol/protocolVersion"
    )
    method = payload.get("method")
    name = params.get("name")

    if isinstance(protocol_version, str):
        headers["MCP-Protocol-Version"] = protocol_version

    if isinstance(method, str):
        headers["Mcp-Method"] = method

    if isinstance(name, str):
        headers["Mcp-Name"] = name

    return headers


# ---------------------------------------------------------------------------
# Main tests
# ---------------------------------------------------------------------------

TESTS = []


def add(cat, name, payload):
    TESTS.append((cat, name, payload))


# === 1. JSON ================================================================

add("JSON", "corps vide", "")
add("JSON", "pas du JSON du tout", "ceci n'est pas du json")
add(
    "JSON",
    "accolade manquante",
    '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"'
)
add(
    "JSON",
    "virgule en trop",
    '{"jsonrpc": "2.0", "id": 1, "method": "tools/list",}'
)
add(
    "JSON",
    "guillemets simples",
    "{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}"
)
add(
    "JSON",
    "tableau au lieu d'objet",
    "[1, 2, 3]"
)


# === 2. CLEF ================================================================

add(
    "CLEF",
    "jsonrpc manquant",
    {
        "id": 1,
        "method": "tools/list",
        "params": {
            "_meta": META_OK
        }
    }
)

add(
    "CLEF",
    "id manquant",
    {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {
            "_meta": META_OK
        }
    }
)

add(
    "CLEF",
    "method manquant",
    {
        "jsonrpc": "2.0",
        "id": 1,
        "params": {
            "_meta": META_OK
        }
    }
)

add(
    "CLEF",
    "clef inconnue au niveau racine",
    {
        **list_body(),
        "foo": "bar"
    }
)


# -- _meta -------------------------------------------------------------------

add(
    "CLEF",
    "_meta absent (tools/list)",
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
)

add(
    "CLEF",
    "protocolVersion absent dans _meta",
    list_body(
        meta={
            "io.modelcontextprotocol/clientCapabilities": {}
        }
    )
)

add(
    "CLEF",
    "clientCapabilities absent dans _meta",
    list_body(
        meta={
            "io.modelcontextprotocol/protocolVersion": "2026-07-28"
        }
    )
)

add(
    "CLEF",
    "clef en trop dans _meta",
    list_body(
        meta={
            **META_OK,
            "clef_random": "x"
        }
    )
)

add(
    "CLEF",
    "clef en trop dans params (tools/list)",
    list_body(
        extra_top={
            "foo": "bar"
        }
    )
)


# -- tools/call --------------------------------------------------------------

add(
    "CLEF",
    "name manquant (tools/call)",
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "arguments": {
                "filepath": "."
            },
            "_meta": META_OK
        }
    }
)

add(
    "CLEF",
    "arguments manquant (tools/call)",
    call_body(
        name="read_file"
    )
)

add(
    "CLEF",
    "clef en trop dans params (tools/call)",
    call_body(
        extra_top={
            "foo": "bar"
        }
    )
)

add(
    "CLEF",
    "argument obligatoire manquant (filepath)",
    call_body(
        name="read_file",
        arguments={}
    )
)

add(
    "CLEF",
    "argument inconnu envoyé",
    call_body(
        name="read_file",
        arguments={
            "filepath": ".",
            "clef_inconnue": "x"
        }
    )
)


# -- server/discover ---------------------------------------------------------

add(
    "CLEF",
    "_meta absent (server/discover)",
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "server/discover",
        "params": {}
    }
)

add(
    "CLEF",
    "paramètre supplémentaire interdit (server/discover)",
    discover_body(
        extra_top={
            "foo": "bar"
        }
    )
)


# === 3. VALEUR ===============================================================

add(
    "VALEUR",
    "jsonrpc != '2.0'",
    {
        **list_body(),
        "jsonrpc": "1.0"
    }
)

add(
    "VALEUR",
    "id type invalide (liste)",
    {
        **list_body(),
        "id": [1, 2]
    }
)

add(
    "VALEUR",
    "method type invalide (int)",
    {
        **list_body(),
        "method": 123
    }
)

add(
    "VALEUR",
    "method inconnue",
    {
        **list_body(),
        "method": "tools/foobar"
    }
)

add(
    "VALEUR",
    "protocolVersion incorrecte",
    list_body(
        meta={
            **META_OK,
            "io.modelcontextprotocol/protocolVersion": "2025-11-25"
        }
    )
)

add(
    "VALEUR",
    "clientCapabilities mauvais type",
    list_body(
        meta={
            **META_OK,
            "io.modelcontextprotocol/clientCapabilities": "pas_un_dict"
        }
    )
)

add(
    "VALEUR",
    "name type invalide (tools/call)",
    call_body(
        name=123
    )
)

add(
    "VALEUR",
    "name inexistant (tool inconnu)",
    call_body(
        name="tool_qui_nexiste_pas"
    )
)

add(
    "VALEUR",
    "arguments mauvais type (pas un dict)",
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "read_file",
            "arguments": "pas_un_dict",
            "_meta": META_OK
        }
    }
)

add(
    "VALEUR",
    "argument filepath mauvais type (int au lieu de str)",
    call_body(
        name="read_file",
        arguments={
            "filepath": 123
        }
    )
)

add(
    "VALEUR",
    "start_line mauvais type (str au lieu d'int)",
    call_body(
        name="read_file",
        arguments={
            "filepath": ".",
            "start_line": "cinq"
        }
    )
)


# === 4. TESTS DES TOOLS =====================================================

add(
    "VALEUR",
    "test read_file",
    call_body(
        name="read_file",
        arguments={
            "filepath": "DevNotes.txt",
            "start_line": 0,
            "end_line": 5
        }
    )
)

add(
    "VALEUR",
    "test list_files",
    call_body(
        name="list_files",
        arguments={
            "directory": "."
        }
    )
)

add(
    "VALEUR",
    "test search_function_or_class_definition_in_code",
    call_body(
        name="search_function_or_class_definition_in_code",
        arguments={
            "name": "message"
        }
    )
)

add(
    "VALEUR",
    "test run_tests",
    call_body(
        name="run_tests"
    )
)

add(
    "VALEUR",
    "test server/discover",
    discover_body()
)


# === 5. TESTS DES HEADERS ===================================================

HEADER_TESTS = []


HEADER_TESTS.append(
    (
        "CLEF",
        "header protocolVersion manquant",
        list_body(),
        {
            "Content-Type": "application/json",
            "Mcp-Method": "tools/list"
        }
    )
)

HEADER_TESTS.append(
    (
        "VALEUR",
        "header protocolVersion incorrect",
        list_body(),
        {
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-11-25",
            "Mcp-Method": "tools/list"
        }
    )
)

HEADER_TESTS.append(
    (
        "CLEF",
        "header method manquant",
        list_body(),
        {
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2026-07-28"
        }
    )
)

HEADER_TESTS.append(
    (
        "VALEUR",
        "header method incorrect",
        list_body(),
        {
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "tools/call"
        }
    )
)

HEADER_TESTS.append(
    (
        "CLEF",
        "header name manquant",
        call_body(
            name="read_file",
            arguments={
                "filepath": "."
            }
        ),
        {
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "tools/call"
        }
    )
)

HEADER_TESTS.append(
    (
        "VALEUR",
        "header name incorrect",
        call_body(
            name="read_file",
            arguments={
                "filepath": "."
            }
        ),
        {
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "tools/call",
            "Mcp-Name": "list_files"
        }
    )
)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def print_response(response):
    print(f"\nSTATUS: {response.status_code}")
    print("RESPONSE:")

    try:
        data = response.json()

        print(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            )
        )

        try:
            print(data["result"]["content"][0]["text"])
        except Exception:
            pass

    except Exception:
        print(response.text)


def send_request(payload, headers):
    if isinstance(payload, str):
        body_str = payload
    else:
        body_str = json.dumps(payload)

    print(
        "REQUEST HEADERS:\n"
        + json.dumps(
            headers,
            indent=2,
            ensure_ascii=False
        )
    )

    print(f"REQUEST BODY:\n{body_str}")

    try:
        response = httpx.post(
            URL,
            content=body_str,
            headers=headers,
            timeout=20
        )

        print_response(response)

    except httpx.RequestError as e:
        print(f"\n[ERREUR RESEAU] {e}")


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

def run_tests():
    total = len(TESTS) + len(HEADER_TESTS)

    for i, (cat, name, payload) in enumerate(
        TESTS,
        start=1
    ):
        print("=" * 80)
        print(
            f"[TEST {i}/{total}] "
            f"CATEGORIE: {cat}  |  {name}"
        )
        print("-" * 80)

        headers = headers_for_payload(payload)

        send_request(
            payload,
            headers
        )

        print("=" * 80)
        print()

    offset = len(TESTS)

    for i, (cat, name, payload, headers) in enumerate(
        HEADER_TESTS,
        start=offset + 1
    ):
        print("=" * 80)
        print(
            f"[TEST {i}/{total}] "
            f"CATEGORIE: {cat}  |  {name}"
        )
        print("-" * 80)

        send_request(
            payload,
            headers
        )

        print("=" * 80)
        print()

    print(f"\n{total} tests exécutés.")


if __name__ == "__main__":
    run_tests()
