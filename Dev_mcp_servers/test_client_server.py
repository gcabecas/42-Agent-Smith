import httpx
import json

URL = "http://127.0.0.1:8042/"

META_OK = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {}
}

# ---------------------------------------------------------------------------
# Helpers pour construire des corps de requête valides comme base
# ---------------------------------------------------------------------------

def list_body(meta=META_OK, extra_top=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
            "params": {"_meta": meta}}
    if extra_top:
        body["params"].update(extra_top)
    return body


def call_body(name="read_file", arguments=None, meta=META_OK, extra_top=None):
    if arguments is None:
   #     arguments = {"filepath": "."}
        body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": name, "_meta": meta}}
    else:
        body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": name, "arguments": arguments, "_meta": meta}}
    if extra_top:
        body["params"].update(extra_top)
    return body


def discover_body(with_params=False):
    body = {"jsonrpc": "2.0", "id": 3, "method": "server/discover"}
    if with_params:
        body["params"] = {}
    return body


# ---------------------------------------------------------------------------
# Liste des tests : (categorie, nom, payload_str_ou_dict)
# categorie in {"JSON", "CLEF", "VALEUR"}
# ---------------------------------------------------------------------------

TESTS = []

def add(cat, name, payload):
    TESTS.append((cat, name, payload))


# === 1. CATEGORIE JSON : corps illisible / mal formé ========================
add("JSON", "corps vide", "")
add("JSON", "pas du JSON du tout", "ceci n'est pas du json")
add("JSON", "accolade manquante", '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"')
add("JSON", "virgule en trop", '{"jsonrpc": "2.0", "id": 1, "method": "tools/list",}')
add("JSON", "guillemets simples", "{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}")
add("JSON", "tableau au lieu d'objet", '[1, 2, 3]')

# === 2. CATEGORIE CLEF : clés manquantes / clés interdites ==================

# -- enveloppe de base --
add("CLEF", "jsonrpc manquant", {"id": 1, "method": "tools/list", "params": {"_meta": META_OK}})
add("CLEF", "id manquant", {"jsonrpc": "2.0", "method": "tools/list", "params": {"_meta": META_OK}})
add("CLEF", "method manquant", {"jsonrpc": "2.0", "id": 1, "params": {"_meta": META_OK}})
add("CLEF", "clef inconnue au niveau racine", {**list_body(), "foo": "bar"})

# -- _meta --
add("CLEF", "_meta absent (tools/list)", {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
add("CLEF", "protocolVersion absent dans _meta",
    list_body(meta={"io.modelcontextprotocol/clientCapabilities": {}}))
add("CLEF", "clientCapabilities absent dans _meta",
    list_body(meta={"io.modelcontextprotocol/protocolVersion": "2026-07-28"}))
add("CLEF", "clef en trop dans _meta",
    list_body(meta={**META_OK, "clef_random": "x"}))
add("CLEF", "clef en trop dans params (tools/list)",
    list_body(extra_top={"foo": "bar"}))

# -- tools/call --
add("CLEF", "name manquant (tools/call)",
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"arguments": {"filepath": "."}, "_meta": META_OK}})
add("CLEF", "arguments manquant (tools/call)",
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "read_file", "_meta": META_OK}})
add("CLEF", "clef en trop dans params (tools/call)",
    call_body(extra_top={"foo": "bar"}))
add("CLEF", "argument obligatoire manquant (filepath)",
    call_body(name="read_file", arguments={}))
add("CLEF", "argument inconnu envoyé", call_body(name="read_file",
    arguments={"filepath": ".", "clef_inconnue": "x"}))

# -- server/discover --
add("CLEF", "params présent (interdit sur server/discover)", discover_body(with_params=True))


# === 3. CATEGORIE VALEUR : clés présentes mais valeur invalide ==============

add("VALEUR", "jsonrpc != '2.0'", {**list_body(), "jsonrpc": "1.0"})
add("VALEUR", "id type invalide (liste)", {**list_body(), "id": [1, 2]})
add("VALEUR", "method type invalide (int)", {**list_body(), "method": 123})
add("VALEUR", "method inconnue", {**list_body(), "method": "tools/foobar"})
add("VALEUR", "protocolVersion incorrecte",
    list_body(meta={**META_OK, "io.modelcontextprotocol/protocolVersion": "2025-11-25"}))
add("VALEUR", "clientCapabilities mauvais type",
    list_body(meta={**META_OK, "io.modelcontextprotocol/clientCapabilities": "pas_un_dict"}))
add("VALEUR", "name type invalide (tools/call)", call_body(name=123))
add("VALEUR", "name inexistant (tool inconnu)", call_body(name="tool_qui_nexiste_pas"))
add("VALEUR", "arguments mauvais type (pas un dict)",
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
     "params": {"name": "read_file", "arguments": "pas_un_dict", "_meta": META_OK}})
add("VALEUR", "argument filepath mauvais type (int au lieu de str)",
    call_body(name="read_file", arguments={"filepath": 123}))
add("VALEUR", "start_line mauvais type (str au lieu d'int)",
    call_body(name="read_file", arguments={"filepath": ".", "start_line": "cinq"}))


# === 4. Tests tools ==============

add("VALEUR", "test read_file",
    call_body(name="read_file", arguments={"filepath": "DevNotes.txt", "start_line": 0, "end_line": 5}))

add("VALEUR", "test list_files",
    call_body(name="list_files", arguments={"directory": "."}))

add("VALEUR", "test search_function_or_class_definition_in_code",
    call_body(name="search_function_or_class_definition_in_code", arguments={"name": "message"}))

add("VALEUR", "test run_tests",
    call_body(name="run_tests"))

# ---------------------------------------------------------------------------
# Exécution
# ---------------------------------------------------------------------------

def run_tests():
    total = len(TESTS)
    for i, (cat, name, payload) in enumerate(TESTS, start=1):
        print("=" * 80)
        print(f"[TEST {i}/{total}] CATEGORIE: {cat}  |  {name}")
        print("-" * 80)

        if isinstance(payload, str):
            body_str = payload
        else:
            body_str = json.dumps(payload)

        print(f"REQUEST BODY:\n{body_str}")

        try:
            r = httpx.post(URL, data=body_str, timeout=20)
            print(f"\nSTATUS: {r.status_code}")
            print(f"RESPONSE:")
            try:
                data = r.json()
                print(json.dumps(data, indent=2, ensure_ascii=False))
                try:
                    print(data["result"]["content"][0]["text"])
                except:
                    pass
            except Exception:
                print(r.text)
        except httpx.RequestError as e:
            print(f"\n[ERREUR RESEAU] {e}")

        print("=" * 80)
        print()

    print(f"\n{total} tests exécutés.")


if __name__ == "__main__":
    run_tests()
