import builtins


def _is_authorized(name: str, authorized_imports: list[str]) -> bool:
    for entry in authorized_imports:
        if entry == name:
            return True
        if entry.endswith(".*"):
            prefix = entry[:-2]
            if name.startswith(prefix + "."):
                return True
    return False


def restricted_import(authorized_imports, name, *args):
    if not _is_authorized(name, authorized_imports):
        raise ImportError(f"import of '{name}' is not authorized")
    return builtins.__import__(name, *args)
