from mcp.types import Prompt, Resource, Tool

from src.common.models import SandboxConfig


def _signature(tool: Tool) -> str:
    properties = tool.input_schema.get("properties", {})
    required = tool.input_schema.get("required", [])
    params = []
    for name, schema in properties.items():
        param = f"{name}: {schema.get('type', 'any')}"
        params.append(param if name in required else f"{param} = None")
    return f"{tool.name}({', '.join(params)})"


def build_manual(config: SandboxConfig, specs: list[Tool],
                 resources: list[Resource] = [],
                 prompts: list[Prompt] = []) -> str:
    lines = [
        "You are running Python code in a sandbox.",
        f"- Authorized imports: {', '.join(config.authorized_imports)}",
        f"- Writable directories: {', '.join(config.allowed_directories)}",
        f"- Limits: {config.max_execution_time_seconds}s per execution, "
        f"{config.max_memory_mb} MB of memory",
        "- Each execution shares the same namespace; stdout and stderr "
        "are returned to you.",
        "- Call final_answer(value) to submit your final result.",
        "",
        "Available tools (call them as Python functions):",
    ]
    for tool in specs:
        lines.append(f"- {_signature(tool)} -> {tool.description}")
    if resources:
        lines += ["", "Available resources (read_resource(uri) -> str):"]
        for resource in resources:
            lines.append(f"- {resource.uri} -> {resource.description}")
    if prompts:
        lines += ["", "Available prompts (get_prompt(name, **args) -> str):"]
        for prompt in prompts:
            args = ", ".join(a.name for a in prompt.arguments or [])
            lines.append(f"- {prompt.name}({args}) -> {prompt.description}")
    return "\n".join(lines)
