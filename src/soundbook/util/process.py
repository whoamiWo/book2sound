"""Thin subprocess helpers for ffmpeg/ffprobe.

Every call site passes an explicit argv list; nothing is ever run through a
shell, so Chinese book titles and paths with spaces or colons are safe.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def stdout_text(self) -> str:
        return self.stdout.decode("utf-8", "replace")

    @property
    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", "replace")


class CommandError(RuntimeError):
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        tail = result.stderr_text.strip().splitlines()[-5:]
        super().__init__(
            f"command failed (exit {result.returncode}): {' '.join(result.argv[:6])} …\n"
            + "\n".join(tail)
        )


def run(argv: list[str], *, stdin: bytes | None = None, check: bool = True) -> CommandResult:
    proc = subprocess.run(
        argv,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    result = CommandResult(argv=list(argv), returncode=proc.returncode,
                           stdout=proc.stdout, stderr=proc.stderr)
    if check and proc.returncode != 0:
        raise CommandError(result)
    return result
