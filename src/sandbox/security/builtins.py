import builtins

_SAFE_NAMES = {
    "abs", "all", "any", "bin", "bool", "chr", "complex", "dict",
    "enumerate", "filter", "float", "format", "int", "isinstance", "len",
    "list", "map", "max", "min", "next", "ord", "pow", "range",
    "reversed", "round", "set", "sorted", "str", "sum", "tuple", "type",
    "zip",
    "print", "__build_class__",
    "True", "False", "None", "NotImplemented", "Ellipsis",
}


SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_NAMES}
SAFE_BUILTINS.update({
    name: obj for name, obj in vars(builtins).items()
    if isinstance(obj, type) and issubclass(obj, BaseException)
})
