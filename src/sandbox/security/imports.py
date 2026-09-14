import builtins
from types import ModuleType
from typing import Any


def _is_authorized(name: str, authorized_imports: list[str]) -> bool:
    for entry in authorized_imports:
        if entry == name or (entry.endswith(".*") and
                             name.startswith(entry[:-1])):
            return True
    return False


def restricted_import(authorized_imports: list[str], name: str,
                      *args: Any) -> ModuleType:
    if not _is_authorized(name, authorized_imports):
        raise ImportError(f"import of '{name}' is not authorized")
    return builtins.__import__(name, *args)
