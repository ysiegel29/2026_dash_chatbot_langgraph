"""Stateless Docker sandbox runner.

The agent keeps all file state in AgentState.virtual_files (base64-encoded).
`run()` materialises those files into a temp dir, executes a command inside
the sandbox container (--network=none), then reads back any changed files.
The container is ephemeral; state is managed entirely outside it.
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    output_files: dict[str, bytes] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def text(self) -> str:
        parts = [f"exit_code={self.exit_code}"]
        if self.stdout:
            parts.append(f"stdout:\n{self.stdout.rstrip()}")
        if self.stderr:
            parts.append(f"stderr:\n{self.stderr.rstrip()}")
        return "\n".join(parts)


def run(
    files: dict[str, str],   # relative path → base64 content
    cmd: list[str],
    timeout: int | None = None,
    workdir: str = "/workspace",
) -> SandboxResult:
    image = os.environ.get("SANDBOX_IMAGE", "deepagent-sandbox:latest")
    timeout = timeout or int(os.environ.get("SANDBOX_TIMEOUT", "60"))

    with tempfile.TemporaryDirectory() as host_dir:
        host_path = Path(host_dir)

        # Materialise virtual FS into temp dir
        for rel_path, b64 in files.items():
            dest = host_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(base64.b64decode(b64))

        docker_cmd = [
            "docker", "run", "--rm",
            "--network=none",                         # no outbound network
            "--memory=1g",
            "--cpus=1.0",
            "--read-only",
            "--tmpfs", "/tmp:size=256m",
            "-v", f"{host_dir}:{workdir}",            # writable workspace (also read back after)
            "--workdir", workdir,
            "-e", "MPLCONFIGDIR=/tmp/matplotlib",     # writable cache dir (root FS is read-only)
            "-e", "HOME=/tmp",                        # generic fallback for tools writing to ~
            image,
            *cmd,
        ]

        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                stdout="",
                stderr=f"Execution timed out after {timeout}s",
                exit_code=124,
            )
        except FileNotFoundError:
            return SandboxResult(
                stdout="",
                stderr="Docker is not available. Make sure Docker is installed and running.",
                exit_code=127,
            )

        # Read back files the sandbox may have written/modified
        output_files: dict[str, bytes] = {}
        for f in host_path.rglob("*"):
            if f.is_file():
                rel = str(f.relative_to(host_path))
                output_files[rel] = f.read_bytes()

        return SandboxResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            output_files=output_files,
        )
