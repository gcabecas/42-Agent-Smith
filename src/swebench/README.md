```
uv run python -m src.swebench --task-file swe_task.json
```

```
list_files(directory=".")
search_function_or_class_definition_in_code(name="__add__")
read_file(filepath="sympy/physics/vector/vector.py", start_line=55, end_line=75)
get_patch()
run_tests()
```
Dumper une autre tâche (`ROOT` car la moulinette veut être lancée depuis son
dossier) :

```
ROOT=$PWD
cd info/given/moulinette/moulinette
uv run moulinette_eval dump swebench --task-id pydata__xarray-4629 --output "$ROOT/swe_task2.json"
cd "$ROOT"
```
