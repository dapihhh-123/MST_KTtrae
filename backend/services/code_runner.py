from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass


@dataclass
class CodeRunResult:
    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool


def _python_executable() -> str:
    return os.environ.get("PYTHON", "python")


def run_python(code: str, mode: str = "run", timeout_sec: float = 2.5) -> CodeRunResult:
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="code_run_") as td:
        if mode == "test":
            filename = os.path.join(td, "student_test.py")
            harness = (
                "\n\n"
                "import sys, traceback\n"
                "_fail = 0\n"
                "for _name, _obj in list(globals().items()):\n"
                "    if callable(_obj) and _name.startswith('test_'):\n"
                "        try:\n"
                "            _obj()\n"
                "            print(f'PASS {_name}')\n"
                "        except Exception as _e:\n"
                "            _fail += 1\n"
                "            print(f'FAIL {_name}: {_e}')\n"
                "            traceback.print_exc()\n"
                "sys.exit(1 if _fail else 0)\n"
            )
            content = code + harness
        else:
            filename = os.path.join(td, "student.py")
            content = code

        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

        cmd = [_python_executable(), "-I", "-S", filename]
        env = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }

        try:
            proc = subprocess.run(
                cmd,
                cwd=td,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            ok = exit_code == 0
            timed_out = False
        except subprocess.TimeoutExpired as e:
            exit_code = None
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            ok = False
            timed_out = True

    duration_ms = int((time.time() - started) * 1000)
    return CodeRunResult(
        ok=ok,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )
