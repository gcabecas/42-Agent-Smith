import builtins

# moulinette/mbpp/data/sanitized_tasks.json c'est les taches qui peuvent nous etre donné, 
# j'ai envoyé a une ia pour recup la liste des builtin utilisé, et créé cette liste, 
# sinon je sais pas quoi mettre, j'ai rien trouvé sur le net et je suis pas dev python securité depuis 16 ans mdr


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
