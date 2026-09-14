import builtins

_DANGEROUS = {
    "eval", "exec", "compile", "open", "__import__",
    "globals", "locals", "input", "breakpoint",
    "exit", "quit", "help",
}

SAFE_BUILTINS = {
    name: obj for name, obj in vars(builtins).items()
    if name not in _DANGEROUS
}
