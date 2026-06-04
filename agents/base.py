from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class TokenExhaustionError(RuntimeError):
    """Raised when an agent CLI rejects a prompt because the context is too large."""


class BaseAgent:
    name = "base"
    default_args: list[str] = []
    token_exhaustion_markers = (
        "context length exceeded",
        "context_length_exceeded",
        "context window",
        "exceed context",
        "exceeds context",
        "exceeded maximum context",
        "maximum context length",
        "maximum context",
        "too many tokens",
        "token limit",
        "tokens exceed",
        "input is too long",
        "prompt is too long",
        "reduce the length",
        "model maximum",
    )

    def __init__(self, project_path: Path, config: dict[str, Any], role: str) -> None:
        self.project_path = project_path
        self.config = config
        self.role = role
        self.cli = config["cli"]

    def initialize(self, codegraph: str) -> str:
        return f"Codegraph loaded. Ready.\n\n{self.short_codegraph_status(codegraph)}"

    def call(self, context_package: str) -> str:
        prompt = self.build_prompt(context_package, mode="respond")
        return self.run_cli(prompt, timeout=300, max_timeout=900)

    def reinitialize(self, codegraph: str, summary: str, state: dict[str, Any]) -> str:
        prompt = self.build_prompt(
            "\n\n".join(
                [
                    "[SESSION RESUME]",
                    codegraph,
                    "[COMPRESSED PRIOR CONTEXT]",
                    summary,
                    "[STATE]",
                    json.dumps(state, indent=2),
                ]
            ),
            mode="resume",
        )
        return self.run_cli(prompt, timeout=120)

    def execute(self, context_package: str) -> str:
        prompt = self.build_prompt(context_package, mode="execute")
        return self.run_cli(prompt, timeout=600, max_timeout=1200)

    def build_prompt(self, context: str, mode: str) -> str:
        if mode == "execute":
            instruction = "Execute the approved proposal. Report what changed and end with >>> TASK_COMPLETE or >>> BLOCKED."
        elif mode == "resume":
            instruction = "Resume from the compressed context. Confirm readiness or ask a focused question."
        else:
            instruction = (
                "Respond with analysis or action. If proposing a plan, end with >>> PROPOSAL. "
                "If you need user input, end with >>> QUESTION. If handing off, end with >>> HANDOFF. "
                "If another agent has fully addressed the task and you have nothing materially different "
                "to add, end with >>> SKIP. If complete, end with >>> TASK_COMPLETE. "
                "If blocked, end with >>> BLOCKED."
            )
        return f"{self.role}\n\n{context}\n\n{instruction}\n"

    def command(self) -> list[str]:
        return [self.cli, *self.default_args]

    def run_cli(
        self,
        prompt: str,
        timeout: float = 120,
        idle_timeout: float | None = None,
        max_timeout: float | None = None,
    ) -> str:
        command = self.command()
        use_shell = os.name == "nt"
        run_command = subprocess.list2cmdline(command) if use_shell else command
        env = os.environ.copy()
        env["CHATBOKS"] = "1"
        if max_timeout is None:
            max_timeout = timeout
        if idle_timeout is None:
            idle_timeout = float(self.config.get("idle_timeout", timeout))
        idle_timeout = float(idle_timeout)
        max_timeout = float(max_timeout)
        extra: dict[str, Any] = {}
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE - inherited by child processes
            extra["startupinfo"] = si
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = subprocess.Popen(
            run_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.project_path,
            encoding="utf-8",
            errors="replace",
            shell=use_shell,
            env=env,
            **extra,
        )
        output_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        def read_stream(name: str, stream: Any) -> None:
            try:
                while True:
                    chunk = stream.read(1)
                    if not chunk:
                        break
                    output_queue.put((name, chunk))
            finally:
                stream.close()

        readers = [
            threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()

        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        started_at = time.monotonic()
        last_output_at = started_at
        timeout_reason: str | None = None

        while True:
            received_output = False
            try:
                while True:
                    stream_name, chunk = output_queue.get_nowait()
                    received_output = True
                    if stream_name == "stdout":
                        stdout_parts.append(chunk)
                    else:
                        stderr_parts.append(chunk)
            except queue.Empty:
                pass
            if received_output:
                last_output_at = time.monotonic()

            if process.poll() is not None and output_queue.empty():
                break

            now = time.monotonic()
            if max_timeout is not None and now - started_at >= max_timeout:
                timeout_reason = "max"
                break
            if idle_timeout is not None and now - last_output_at >= idle_timeout:
                timeout_reason = "idle"
                break
            time.sleep(0.01)

        if timeout_reason:
            self.terminate_process(process)
            self.drain_output(output_queue, stdout_parts, stderr_parts, process, 0.5)
            combined_output = "\n".join(
                part.strip()
                for part in ("".join(stderr_parts), "".join(stdout_parts))
                if part.strip()
            )
            if self.is_token_exhaustion(combined_output):
                raise TokenExhaustionError(
                    combined_output or f"{self.name} exhausted its token context."
                )
            if timeout_reason == "idle":
                return (
                    f"CLI call idle timed out for {self.name} after {idle_timeout} seconds."
                    "\n>>> BLOCKED"
                )
            return f"CLI call timed out for {self.name} after {max_timeout} seconds.\n>>> BLOCKED"

        returncode = process.wait()
        for reader in readers:
            reader.join(timeout=0.2)
        self.drain_output(output_queue, stdout_parts, stderr_parts, process, 0.2)

        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
        if returncode != 0:
            combined_output = "\n".join(
                part.strip() for part in (stderr, stdout) if part.strip()
            )
            if self.is_token_exhaustion(combined_output):
                raise TokenExhaustionError(
                    combined_output or f"{self.name} exhausted its token context."
                )
            error_output = stderr.strip() or "No stderr captured."
            return f"CLI call failed for {self.name}: {error_output}\n>>> BLOCKED"
        output = stdout.strip()
        if self.is_token_exhaustion(output):
            raise TokenExhaustionError(output)
        return output or f"{self.name} returned no output.\n>>> BLOCKED"

    @staticmethod
    def drain_output(
        output_queue: queue.Queue[tuple[str, str]],
        stdout_parts: list[str],
        stderr_parts: list[str],
        process: subprocess.Popen[str],
        timeout: float,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            drained = False
            try:
                while True:
                    stream_name, chunk = output_queue.get_nowait()
                    drained = True
                    if stream_name == "stdout":
                        stdout_parts.append(chunk)
                    else:
                        stderr_parts.append(chunk)
            except queue.Empty:
                pass
            if process.poll() is not None and output_queue.empty():
                break
            if not drained:
                time.sleep(0.01)

    @staticmethod
    def terminate_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            return
        process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def short_codegraph_status(codegraph: str) -> str:
        for line in codegraph.splitlines():
            if line.startswith("Files ") or line.startswith("[CODEGRAPH] Not available"):
                return line
        return "Codegraph summary included."

    @classmethod
    def is_token_exhaustion(cls, text: str) -> bool:
        normalized = text.lower()
        return any(marker in normalized for marker in cls.token_exhaustion_markers)
