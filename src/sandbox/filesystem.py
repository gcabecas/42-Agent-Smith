import os


def _is_authorized(path: str, allowed_directories: list[str]) -> bool:
    resolved = os.path.realpath(path)
    for directory in allowed_directories:
        allowed = os.path.realpath(directory)
        if resolved == allowed or resolved.startswith(allowed + os.sep):
            return True
    return False


def restricted_open(allowed_directories, file, *args, **kwargs):
    if not _is_authorized(file, allowed_directories):
        raise PermissionError(f"access to '{file}' is not authorized")
    return open(file, *args, **kwargs)
