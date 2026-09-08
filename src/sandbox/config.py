import json
from pathlib import Path

from src.common.models import SandboxConfig


def load_config(path: str) -> SandboxConfig:
    try:
        data = json.loads(Path(path).read_text())
    except OSError as e:
        raise ValueError(str(e)) from e
    return SandboxConfig.model_validate(data)
