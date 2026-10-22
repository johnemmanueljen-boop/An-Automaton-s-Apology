"""Explicit execution policies for Lean; disabled by default, isolated Docker when configured."""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LeanExecution:
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    seconds: float = 0.0
    mode: str = "disabled"

    @property
    def output(self):
        return self.stdout + "\n" + self.stderr


def execute_lean(repo: Path, source: str, timeout: int = 120) -> LeanExecution:
    mode = os.environ.get("APOLOGY_LEAN_MODE", "disabled")
    if mode not in {"docker", "local"}:
        return LeanExecution(stderr="Lean execution disabled; configure Docker or explicitly select trusted local execution")
    if mode == "local" and os.environ.get("APOLOGY_TRUST_LOCAL_LEAN") != "1":
        return LeanExecution(stderr="local execution requires APOLOGY_TRUST_LOCAL_LEAN=1 for trusted input", mode=mode)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="apology-lean-") as tmp:
        source_path = Path(tmp, "Probe.lean")
        source_path.write_text(source, encoding="utf-8")
        if mode == "docker":
            image = os.environ.get("APOLOGY_LEAN_IMAGE", "")
            if not image or "@sha256:" not in image:
                return LeanExecution(stderr="APOLOGY_LEAN_IMAGE must pin an installed image by sha256 digest", mode=mode)
            name = "apology-" + source_path.parent.name.lower().replace("_", "-")
            cmd = ["docker", "run", "--rm", "--name", name, "--pull=never", "--network=none", "--read-only",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1", "--memory=2g", "--pids-limit=128",
                   "--tmpfs", "/tmp:rw,nosuid,size=256m", "--mount", f"type=bind,source={repo.resolve()},target=/repo,readonly",
                   "--mount", f"type=bind,source={source_path.parent},target=/input,readonly", "--workdir", "/repo",
                   image, "lake", "env", "lean", "/input/Probe.lean"]
            env = None  # no host variables are forwarded to the container
        else:
            cmd = ["lake", "env", "lean", str(source_path)]
            env = {key: value for key, value in os.environ.items()
                   if not any(secret in key.upper() for secret in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
            env["PATH"] = str(Path.home() / ".elan" / "bin") + os.pathsep + os.environ.get("PATH", "")
        try:
            proc = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
            return LeanExecution(proc.returncode, proc.stdout, proc.stderr, False, time.monotonic() - start, mode)
        except subprocess.TimeoutExpired:
            if mode == "docker":
                subprocess.run(["docker", "kill", name], capture_output=True, timeout=10)
            return LeanExecution(stderr="execution timed out", timed_out=True,
                                 seconds=time.monotonic() - start, mode=mode)
        except OSError as exc:
            return LeanExecution(stderr=str(exc), seconds=time.monotonic() - start, mode=mode)
