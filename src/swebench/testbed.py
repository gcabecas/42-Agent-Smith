import io
import shlex
import signal
import tarfile
from pathlib import Path
from types import FrameType
from typing import Any

import docker

SERVER_SOURCES = [
    "mcp_tools_swebench.py",
    "src/__init__.py",
    "src/mcp_server",
]
SERVER_PACKAGES = [
    "flask",
    "pydantic",
    "GitPython",
    "jedi",
    "tree-sitter",
    "tree-sitter-language-pack",
]


class DockerTestbed:
    def __init__(
        self,
        image: str,
        workdir: str = "/testbed",
        server_dir: str = "/agent",
        python: str = "python",
        eval_path: str = "/eval.sh",
    ) -> None:
        self.image = image
        self.client = docker.from_env()
        self.workdir = workdir
        self.server_dir = server_dir
        self.python = python
        self.eval_path = eval_path
        self.container: Any = None
        self._previous_handler: Any = signal.SIG_DFL

    def has_image(self) -> bool:
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            return False
        return True

    def start(self) -> None:
        if self.container is not None:
            raise RuntimeError("Docker testbed is already started")

        if not self.has_image():
            self.client.images.pull(self.image)

        self.container = self.client.containers.create(
            image=self.image,
            command=["tail", "-f", "/dev/null"],
            detach=True,
        )
        try:
            self.container.start()
        except Exception:
            self.close()
            raise
        self._previous_handler = signal.signal(signal.SIGTERM, self._terminate)

    def exec(self, command: list[str],
             workdir: str | None = None) -> tuple[int, str]:
        result = self.container.exec_run(
            command, workdir=workdir or self.workdir)
        output = result.output
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return result.exit_code, output

    def copy_in(self) -> None:
        def container_owner(entry: tarfile.TarInfo) -> tarfile.TarInfo:
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = "root"
            return entry

        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            for source in SERVER_SOURCES:
                tar.add(source, arcname=source, filter=container_owner)

        self.exec(["mkdir", "-p", self.server_dir], workdir="/")
        self.container.put_archive(self.server_dir, archive.getvalue())

    def write_eval_script(self, script: str) -> None:
        path = Path(self.eval_path)
        payload = script.replace("\r", "").replace(
            "set -uxo pipefail", "set -uo pipefail").encode()
        entry = tarfile.TarInfo(name=path.name)
        entry.size = len(payload)
        entry.mode = 0o755

        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            tar.addfile(entry, io.BytesIO(payload))

        self.container.put_archive(str(path.parent), archive.getvalue())

    def check_python(self) -> str:
        code, output = self.exec([self.python, "--version"], workdir="/")
        if code != 0:
            raise RuntimeError(
                f"'{self.python}' is not usable in {self.image}: {output}\n"
                "pass a working interpreter with --python"
            )
        return output.strip()

    def install(self) -> None:
        code, output = self.exec(
            [self.python, "-m", "pip", "install", "--quiet", *SERVER_PACKAGES],
            workdir=self.server_dir,
        )
        if code != 0:
            raise RuntimeError(f"pip install failed in container: {output}")

        code, output = self.exec(
            [self.python, "-c", "import src.mcp_server.mcp_server"],
            workdir=self.server_dir,
        )
        if code != 0:
            raise RuntimeError(
                f"server cannot be imported in container, "
                f"SERVER_PACKAGES is probably incomplete: {output}"
            )

    def setup(self, eval_script: str | None = None) -> None:
        self.start()
        self.check_python()
        self.copy_in()
        if eval_script:
            self.write_eval_script(eval_script)
        self.install()

    def mcp_command(self) -> str:
        return " ".join(shlex.quote(part) for part in [
            "docker", "exec", "-i",
            "-w", self.server_dir,
            "-e", f"TESTBED_PATH={self.workdir}",
            "-e", f"EVAL_SCRIPT={self.eval_path}",
            self.container.id,
            self.python, "mcp_tools_swebench.py",
        ])

    def _terminate(self, number: int, frame: FrameType | None) -> None:
        self.close()
        signal.raise_signal(signal.SIGTERM)

    def close(self) -> None:
        signal.signal(signal.SIGTERM, self._previous_handler)
        if self.container is None:
            return

        container = self.container
        self.container = None
        container.remove(force=True)

    def __enter__(self) -> "DockerTestbed":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
