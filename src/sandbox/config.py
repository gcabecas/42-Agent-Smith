import json
from pathlib import Path

from src.common.models import SandboxConfig


def load_config(path: str) -> SandboxConfig:
    data = json.loads(Path(path).read_text())
    return SandboxConfig.model_validate(data)
